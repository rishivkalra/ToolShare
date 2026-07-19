"""Project kits: describe a project, get the tool list matched against
what's actually rentable nearby — the whole kit in one screen."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import geo
from ..auth import current_uid
from ..deps import Container, get_container
from ..models import Listing, ListingStatus
from ..services.project_planner import PlannedTool, ProjectPlan

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

    return ProjectKitResponse(
        plan=plan,
        kit=kit,
        total_estimated_per_day_cents=total,
        missing_tools=missing,
    )
