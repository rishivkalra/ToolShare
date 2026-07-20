"""Internal task handlers, invoked by Cloud Tasks (never by clients).

Auth: X-Internal-Token must match settings.internal_task_secret. In dev the
secret is empty, so the check is skipped for local curl testing. All handlers
are idempotent — Cloud Tasks delivers at-least-once.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import BookingState, ListingStatus
from ..state_machine import transition

router = APIRouter(prefix="/internal/tasks", tags=["internal"])


def _check_token(
    x_internal_token: str = Header(default=""),
    settings: Settings = Depends(get_settings),
):
    if settings.internal_task_secret and x_internal_token != settings.internal_task_secret:
        raise HTTPException(status_code=403, detail="Bad internal token")


class BookingTask(BaseModel):
    booking_id: str


@router.post("/expire-booking", dependencies=[Depends(_check_token)])
def expire_booking(body: BookingTask, c: Container = Depends(get_container)):
    """Fires request_expiry_hours after a booking request; expires it if the
    lender never responded."""
    booking = c.bookings.get(body.booking_id)
    if not booking or booking.state != BookingState.REQUESTED:
        return {"expired": False}  # already handled — idempotent no-op
    transition(booking, BookingState.EXPIRED, "system", "lender did not respond")
    c.bookings.update(booking)
    c.notifier.notify(
        booking.borrower_uid,
        f"Request expired — {booking.listing_title}",
        "The owner didn't respond in 24h. No charge was made.",
        booking_id=booking.id,
    )
    return {"expired": True}


@router.post("/wanted-digest", dependencies=[Depends(_check_token)])
def wanted_digest(c: Container = Depends(get_container)):
    """Weekly (Cloud Scheduler): turn last week's unmet demand into supply.

    Aggregates unmatched searches + kit gaps per neighborhood and tells the
    owners already listing there what neighbors couldn't find.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    by_hood: dict[str, Counter] = defaultdict(Counter)
    for s in c.wanted.since(cutoff):
        by_hood[s.geohash][s.term] += 1

    owners_notified = 0
    for gh, counter in by_hood.items():
        owners = {
            l.owner_uid
            for l in c.listings.by_geohash_prefixes([gh], limit=200)
            if l.status == ListingStatus.ACTIVE
        }
        if not owners:
            continue
        top = counter.most_common(3)
        lines = ", ".join(
            f"{term} ({n} neighbors)" if n > 1 else term for term, n in top
        )
        for owner in owners:
            c.notifier.notify(
                owner,
                "🔥 Wanted near you this week",
                f"Neighbors searched for: {lines}. Own one? Listing takes a "
                "minute — snap a photo and the AI drafts it.",
                kind="system",
            )
            owners_notified += 1
    return {"neighborhoods": len(by_hood), "owners_notified": owners_notified}
