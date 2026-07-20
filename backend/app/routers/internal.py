"""Internal task handlers, invoked by Cloud Tasks (never by clients).

Auth: X-Internal-Token must match settings.internal_task_secret. In dev the
secret is empty, so the check is skipped for local curl testing. All handlers
are idempotent — Cloud Tasks delivers at-least-once.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import BookingState
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
