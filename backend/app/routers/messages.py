from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_uid
from ..deps import Container, get_container
from ..models import Message, MessageCreate
from ..repos.memory import next_id

router = APIRouter(prefix="/v1/bookings/{booking_id}/messages", tags=["messages"])


def _require_participant(booking_id: str, uid: str, c: Container):
    booking = c.bookings.get(booking_id)
    if not booking or uid not in (booking.borrower_uid, booking.lender_uid):
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.post("", response_model=Message, status_code=201)
def send_message(
    booking_id: str,
    body: MessageCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    _require_participant(booking_id, uid, c)
    msg = Message(
        id=next_id("msg"),
        booking_id=booking_id,
        sender_uid=uid,
        text=body.text,
        created_at=datetime.now(timezone.utc),
    )
    return c.messages.create(msg)


@router.get("", response_model=list[Message])
def list_messages(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    _require_participant(booking_id, uid, c)
    return c.messages.for_booking(booking_id)
