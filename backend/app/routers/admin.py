"""Founder console: the reports queue and dispute resolution.

Access is gated by TOOLSHARE_ADMIN_UIDS (comma-separated). Disputes are the
manual half of the ToolShare Guarantee: the deposit was captured when the
claim opened; resolution either refunds the borrower (claim rejected) or
pays the lender and keeps the capture (claim upheld).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_uid
from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import Booking, BookingState, Report
from ..state_machine import TransitionError, transition

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def require_admin(
    uid: str = Depends(current_uid), settings: Settings = Depends(get_settings)
) -> str:
    if uid not in settings.admin_uid_set:
        raise HTTPException(status_code=403, detail="Admin only")
    return uid


class AdminOverview(BaseModel):
    reports: list[Report]
    disputes: list[Booking]


@router.get("/overview", response_model=AdminOverview)
def overview(
    _: str = Depends(require_admin), c: Container = Depends(get_container)
):
    return AdminOverview(
        reports=c.reports.recent(50),
        disputes=c.bookings.by_state(BookingState.DISPUTED, 50),
    )


class ResolveBody(BaseModel):
    outcome: str = Field(pattern="^(refund_borrower|pay_lender)$")
    note: str = Field(default="", max_length=500)


@router.post("/disputes/{booking_id}/resolve", response_model=Booking)
def resolve_dispute(
    booking_id: str,
    body: ResolveBody,
    admin: str = Depends(require_admin),
    c: Container = Depends(get_container),
):
    booking = c.bookings.get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.state != BookingState.DISPUTED:
        raise HTTPException(status_code=409, detail="Booking is not in dispute")

    if body.outcome == "refund_borrower":
        # Claim rejected: hand the captured deposit back, pay the lender the
        # rental as a normal completion would have.
        if booking.stripe_deposit_intent:
            c.payments.refund_rental(booking.stripe_deposit_intent, None)
        _payout(c, booking)
        c.notifier.notify(
            booking.borrower_uid,
            f"Dispute resolved in your favor — {booking.listing_title}",
            "Your deposit has been refunded in full." + (f" Note: {body.note}" if body.note else ""),
            booking_id=booking.id,
        )
        c.notifier.notify(
            booking.lender_uid,
            f"Dispute closed — {booking.listing_title}",
            "The claim wasn't upheld; the rental payout is on its way to you.",
            booking_id=booking.id,
        )
    else:
        # Claim upheld: lender keeps the captured deposit AND the rental.
        _payout(c, booking)
        c.notifier.notify(
            booking.lender_uid,
            f"Dispute resolved in your favor — {booking.listing_title}",
            "The captured deposit stays with you along with the rental payout."
            + (f" Note: {body.note}" if body.note else ""),
            booking_id=booking.id,
        )
        c.notifier.notify(
            booking.borrower_uid,
            f"Dispute closed — {booking.listing_title}",
            "The damage claim was upheld; the deposit covers it. Reply to "
            "support if you want to appeal." + (f" Note: {body.note}" if body.note else ""),
            booking_id=booking.id,
        )

    try:
        transition(booking, BookingState.COMPLETED, "system",
                   f"dispute resolved by {admin}: {body.outcome}")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return c.bookings.update(booking)


def _payout(c: Container, booking: Booking) -> None:
    """Release the rental payout the dispute had paused (if not already paid)."""
    if booking.stripe_transfer_id:
        return
    lender = c.users.get(booking.lender_uid)
    if lender and lender.stripe_connect_id:
        booking.stripe_transfer_id = c.payments.payout_lender(
            lender.stripe_connect_id, booking.price.rental_cents, booking.id
        )
    # No Connect account: payout stays pending, swept at connect/complete.
