"""Project kits: describe a project, get the tool list matched against
what's actually rentable nearby — the whole kit in one screen."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import geo
from ..auth import current_uid
from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import (
    Booking,
    BookingCreate,
    Kit,
    KitItemSnapshot,
    Listing,
    ListingStatus,
    WantedSignal,
)
from ..repos.memory import next_id
from ..services.project_planner import PlannedTool, ProjectPlan
from .bookings import create_booking_request

# Rough "what buying this would cost" anchor for the share page: a tool's
# purchase price is on the order of 35 daily rentals.
BUY_MULTIPLE = 35

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class ProjectPlanRequest(BaseModel):
    description: str = Field(min_length=10, max_length=2000)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=8.0, gt=0, le=50)


class KitItem(BaseModel):
    tool: PlannedTool
    matches: list[Listing]  # nearby listings that could fill this slot, closest first


class ProjectKitResponse(BaseModel):
    plan: ProjectPlan
    kit: list[KitItem]
    total_estimated_per_day_cents: int  # cheapest match per required tool
    missing_tools: list[str]  # required tools with no nearby listing
    kit_id: str = ""  # saved kit — /kit/{kit_id} is its shareable public page
    share_path: str = ""


def _match_listings(
    tool: PlannedTool, candidates: list[Listing], lat: float, lng: float
) -> list[Listing]:
    name_words = set(tool.name.lower().split())
    scored: list[tuple[float, float, Listing]] = []
    for l in candidates:
        if l.status != ListingStatus.ACTIVE:
            continue
        title_words = set(l.title.lower().replace("-", " ").split())
        overlap = len(name_words & title_words)
        category_hit = l.category == tool.category
        if overlap == 0 and not category_hit:
            continue
        dist = geo.haversine_km(lat, lng, l.approx_lat, l.approx_lng)
        # Word overlap dominates; category match is a weak fallback signal.
        scored.append((-(overlap * 10 + (1 if category_hit else 0)), dist, l))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [l for _, _, l in scored[:3]]


@router.post("/plan", response_model=ProjectKitResponse)
def plan_project(
    body: ProjectPlanRequest,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    plan = c.planner.plan(body.description)

    prefixes = geo.cover_prefixes(body.lat, body.lng, body.radius_km)
    candidates = c.listings.by_geohash_prefixes(prefixes)

    kit: list[KitItem] = []
    total = 0
    missing: list[str] = []
    for tool in plan.tools:
        matches = _match_listings(tool, candidates, body.lat, body.lng)
        kit.append(KitItem(tool=tool, matches=matches))
        if matches:
            if not tool.optional:
                # Price the top-ranked match — that's the listing the user
                # actually lands on, not a weak category-only alternative.
                total += matches[0].price_per_day_cents
        elif not tool.optional:
            missing.append(tool.name)

    gh5 = geo.encode(body.lat, body.lng)[:5]
    now = datetime.now(timezone.utc)
    for term in missing:
        c.wanted.create(WantedSignal(
            id=next_id("wnt"), geohash=gh5, term=term.lower()[:60],
            source="kit", uid=uid, created_at=now,
        ))

    # Persist the kit so it has a shareable public page — the viral unit.
    buy_estimate = sum(
        i.matches[0].price_per_day_cents * BUY_MULTIPLE for i in kit if i.matches
    )
    saved = c.kits.create(Kit(
        id=next_id("kit"),
        owner_uid=uid,
        description=body.description.strip()[:300],
        summary=plan.project_summary,
        items=[
            KitItemSnapshot(
                name=i.tool.name, category=i.tool.category, why=i.tool.why,
                optional=i.tool.optional,
                listing_id=i.matches[0].id if i.matches else "",
                listing_title=i.matches[0].title if i.matches else "",
                price_per_day_cents=i.matches[0].price_per_day_cents if i.matches else 0,
                distance_km=round(geo.haversine_km(
                    body.lat, body.lng,
                    i.matches[0].approx_lat, i.matches[0].approx_lng), 1)
                if i.matches else 0.0,
            )
            for i in kit
        ],
        missing=missing,
        total_per_day_cents=total,
        buy_estimate_cents=buy_estimate,
        geohash=gh5,
        created_at=now,
    ))

    return ProjectKitResponse(
        plan=plan,
        kit=kit,
        total_estimated_per_day_cents=total,
        missing_tools=missing,
        kit_id=saved.id,
        share_path=f"/kit/{saved.id}",
    )


class KitCheckoutRequest(BaseModel):
    listing_ids: list[str] = Field(min_length=1, max_length=12)
    start_date: date
    end_date: date


class KitCheckoutItem(BaseModel):
    listing_id: str
    booking_id: str = ""
    error: str = ""


class KitCheckoutResponse(BaseModel):
    items: list[KitCheckoutItem]
    requested: int
    failed: int


@router.post("/checkout", response_model=KitCheckoutResponse)
def kit_checkout(
    body: KitCheckoutRequest,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
    settings: Settings = Depends(get_settings),
):
    """One-tap kit rental: a booking request per listing for the same dates.

    Best-effort per item — one unavailable tool doesn't sink the rest of the
    kit; failures come back with the reason so the app can offer alternatives.
    """
    items: list[KitCheckoutItem] = []
    for listing_id in dict.fromkeys(body.listing_ids):  # dedupe, keep order
        try:
            booking: Booking = create_booking_request(
                c,
                settings,
                uid,
                BookingCreate(
                    listing_id=listing_id,
                    start_date=body.start_date,
                    end_date=body.end_date,
                ),
            )
            items.append(KitCheckoutItem(listing_id=listing_id, booking_id=booking.id))
        except HTTPException as e:
            items.append(KitCheckoutItem(listing_id=listing_id, error=str(e.detail)))
    failed = sum(1 for i in items if i.error)
    return KitCheckoutResponse(items=items, requested=len(items) - failed, failed=failed)
