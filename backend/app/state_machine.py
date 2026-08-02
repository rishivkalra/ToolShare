"""Booking lifecycle state machine.

All booking state changes must flow through `transition()` so that:
- illegal jumps are impossible (e.g. REQUESTED -> COMPLETED),
- only the right party can trigger each change,
- every change is appended to the booking's audit timeline.

Side effects (charges, payouts, notifications) are orchestrated by the
bookings router *around* these transitions, never inside them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .models import Booking, BookingState, TimelineEvent

# role -> set of (from, to) transitions that role may perform
Role = str  # "borrower" | "lender" | "system"

_ALLOWED: dict[Role, set[tuple[BookingState, BookingState]]] = {
    "borrower": {
        (BookingState.REQUESTED, BookingState.CANCELLED_BY_BORROWER),
        (BookingState.APPROVED, BookingState.CANCELLED_BY_BORROWER),
        (BookingState.CONFIRMED, BookingState.CANCELLED_BY_BORROWER),
    },
    "lender": {
        (BookingState.REQUESTED, BookingState.APPROVED),
        (BookingState.REQUESTED, BookingState.DECLINED),
        (BookingState.CONFIRMED, BookingState.CANCELLED_BY_LENDER),
        (BookingState.CONFIRMED, BookingState.PICKED_UP),
        (BookingState.PICKED_UP, BookingState.RETURNED),
        (BookingState.RETURNED, BookingState.DISPUTED),
    },
    "system": {
        (BookingState.REQUESTED, BookingState.EXPIRED),
        # APPROVED whose payment never completed: expired by the same 24h
        # task so a failed charge can't block the calendar forever.
        (BookingState.APPROVED, BookingState.EXPIRED),
        (BookingState.APPROVED, BookingState.CONFIRMED),
        (BookingState.RETURNED, BookingState.COMPLETED),
        (BookingState.DISPUTED, BookingState.COMPLETED),
    },
}


class TransitionError(Exception):
    def __init__(self, booking: Booking, to_state: BookingState, role: Role):
        self.from_state = booking.state
        self.to_state = to_state
        self.role = role
        super().__init__(
            f"{role} may not move booking from {booking.state.value} to {to_state.value}"
        )


def role_of(booking: Booking, uid: str) -> Optional[Role]:
    if uid == "system":
        return "system"
    if uid == booking.borrower_uid:
        return "borrower"
    if uid == booking.lender_uid:
        return "lender"
    return None


def can_transition(booking: Booking, to_state: BookingState, role: Role) -> bool:
    return (booking.state, to_state) in _ALLOWED.get(role, set())


def transition(
    booking: Booking,
    to_state: BookingState,
    actor_uid: str,
    note: str = "",
) -> Booking:
    """Apply a state transition in place; raises TransitionError if illegal.

    Idempotency: transitioning to the current state is a no-op (returns the
    booking unchanged) so retried webhook deliveries and double-taps are safe.
    """
    if booking.state == to_state:
        return booking

    role = role_of(booking, actor_uid)
    if role is None or not can_transition(booking, to_state, role):
        raise TransitionError(booking, to_state, role or "stranger")

    booking.timeline.append(
        TimelineEvent(
            at=datetime.now(timezone.utc),
            actor_uid=actor_uid,
            from_state=booking.state,
            to_state=to_state,
            note=note,
        )
    )
    booking.state = to_state
    return booking
