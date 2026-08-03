"""Neighborhood identity: density stats, savings counters, unmet demand.

The moat is per-neighborhood liquidity — these numbers make it visible
("Maple St: 212 tools, $14k of purchases avoided") and the unlock target
turns density itself into the growth game.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .. import geo
from ..deps import Container, get_container
from ..models import BookingState, ListingStatus

router = APIRouter(prefix="/v1/neighborhoods", tags=["neighborhoods"])

UNLOCK_TARGET = 40  # listings that make a neighborhood feel alive
BUY_MULTIPLE = 35   # a tool's purchase price ≈ 35 daily rentals

_COUNTED_STATES = {
    BookingState.CONFIRMED, BookingState.PICKED_UP,
    BookingState.RETURNED, BookingState.COMPLETED, BookingState.DISPUTED,
}


class WantedTerm(BaseModel):
    term: str
    count: int


class NeighborhoodStats(BaseModel):
    geohash: str
    listings: int
    lenders: int
    rentals: int
    days_on_loan: int
    saved_cents: int  # Σ max(0, est. purchase price − rental paid)
    unlock_target: int
    unlocked: bool
    wanted: list[WantedTerm]
    page_path: str


def compute_stats(c: Container, gh5: str) -> NeighborhoodStats:
    listings = [
        l for l in c.listings.by_geohash_prefixes([gh5], limit=500)
        if l.status == ListingStatus.ACTIVE
    ]
    lenders = {l.owner_uid for l in listings}
    rentals = days = saved = 0
    for l in listings[:200]:
        for b in c.bookings.by_listing(l.id):
            if b.state in _COUNTED_STATES:
                rentals += 1
                days += b.price.days
                saved += max(0, l.price_per_day_cents * BUY_MULTIPLE - b.price.rental_cents)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    counter: Counter[str] = Counter(
        s.term for s in c.wanted.since(cutoff) if s.geohash == gh5
    )
    wanted = [WantedTerm(term=t, count=n) for t, n in counter.most_common(6)]

    return NeighborhoodStats(
        geohash=gh5,
        listings=len(listings),
        lenders=len(lenders),
        rentals=rentals,
        days_on_loan=days,
        saved_cents=saved,
        unlock_target=UNLOCK_TARGET,
        unlocked=len(listings) >= UNLOCK_TARGET,
        wanted=wanted,
        page_path=f"/n/{gh5}",
    )


class PulseEvent(BaseModel):
    icon: str
    text: str
    when: str  # ISO timestamp for client-side "2h ago"


class Pulse(BaseModel):
    events: list[PulseEvent]
    saved_this_week_cents: int


def compute_pulse(c: Container, gh5: str, limit: int = 12) -> Pulse:
    """The daily-relevance feed (the Nextdoor lesson): fresh, local, human.
    Derived live from listings and bookings — no extra writes."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    events: list[tuple[str, PulseEvent]] = []

    listings = [
        l for l in c.listings.by_geohash_prefixes([gh5], limit=500)
        if l.status == ListingStatus.ACTIVE
    ]
    names: dict[str, str] = {}

    def name_of(uid: str) -> str:
        if uid not in names:
            u = c.users.get(uid)
            names[uid] = (u.display_name if u and u.display_name else "A neighbor")
        return names[uid]

    saved_week = 0
    for l in listings:
        if l.created_at and l.created_at >= week_ago:
            events.append((l.created_at.isoformat(), PulseEvent(
                icon="🆕", when=l.created_at.isoformat(),
                text=f"{name_of(l.owner_uid)} listed a {l.title} — "
                     f"${l.price_per_day_cents / 100:.0f}/day",
            )))
    for l in listings[:200]:
        for b in c.bookings.by_listing(l.id):
            if b.state != BookingState.COMPLETED or not b.timeline:
                continue
            done_at = b.timeline[-1].at
            if done_at and done_at >= week_ago:
                saved = max(0, l.price_per_day_cents * BUY_MULTIPLE - b.price.rental_cents)
                saved_week += saved
                events.append((done_at.isoformat(), PulseEvent(
                    icon="🤝", when=done_at.isoformat(),
                    text=f"{name_of(b.borrower_uid)} borrowed the {l.title} "
                         f"from {name_of(b.lender_uid)} — saved ~${saved / 100:.0f} vs buying",
                )))

    events.sort(key=lambda t: t[0], reverse=True)
    return Pulse(events=[e for _, e in events[:limit]],
                 saved_this_week_cents=saved_week)


@router.get("/pulse", response_model=Pulse)
def pulse(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    c: Container = Depends(get_container),
):
    return compute_pulse(c, geo.encode(lat, lng)[:5])


@router.get("", response_model=NeighborhoodStats)
def neighborhood(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    c: Container = Depends(get_container),
):
    return compute_stats(c, geo.encode(lat, lng)[:5])
