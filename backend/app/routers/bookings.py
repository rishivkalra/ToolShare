"""Booking lifecycle endpoints.

The money loop:
  POST /v1/bookings                      borrower requests dates   -> REQUESTED
  POST /v1/bookings/{id}/approve         lender accepts; we charge -> CONFIRMED
  POST /v1/bookings/{id}/decline         lender rejects            -> DECLINED
  POST /v1/bookings/{id}/cancel          either side cancels       -> CANCELLED_*
  POST /v1/bookings/{id}/pickup          both sides confirm        -> PICKED_UP
  POST /v1/bookings/{id}/return          lender confirms return    -> RETURNED
                                          payout + deposit void    -> COMPLETED
  POST /v1/bookings/{id}/dispute         lender reports damage     -> DISPUTED
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_uid
from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import (
    Booking,
    BookingCreate,
    BookingState,
    ListingStatus,
    TimelineEvent,
    UserProfile,
)
from ..pricing import price_booking
from ..repos.memory import next_id
from ..state_machine import TransitionError, transition

router = APIRouter(prefix="/v1/bookings", tags=["bookings"])


def _get_booking_for(booking_id: str, uid: str, c: Container) -> Booking:
    booking = c.bookings.get(booking_id)
    if not booking or uid not in (booking.borrower_uid, booking.lender_uid):
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _transition_or_409(booking: Booking, to_state: BookingState, actor: str, note: str = ""):
    try:
        transition(booking, to_state, actor, note)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


def create_booking_request(
    c: Container, settings: Settings, uid: str, body: BookingCreate
) -> Booking:
    """Shared by single-booking requests and project-kit checkout."""
    listing = c.listings.get(body.listing_id)
    if not listing or listing.status != ListingStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Listing not available")
    if listing.owner_uid == uid:
        raise HTTPException(status_code=400, detail="You can't rent your own tool")
    if c.bookings.overlapping(body.listing_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="Those dates are already booked")

    booking = Booking(
        id=next_id("bkg"),
        listing_id=listing.id,
        listing_title=listing.title,
        borrower_uid=uid,
        lender_uid=listing.owner_uid,
        start_date=body.start_date,
        end_date=body.end_date,
        price=price_booking(
            settings,
            listing.price_per_day_cents,
            listing.deposit_cents,
            body.start_date,
            body.end_date,
        ),
        created_at=datetime.now(timezone.utc),
    )
    booking.timeline.append(
        TimelineEvent(
            at=datetime.now(timezone.utc),
            actor_uid=uid,
            from_state=None,
            to_state=BookingState.REQUESTED,
            note="requested",
        )
    )
    c.bookings.create(booking)
    c.tasks.schedule(
        "/internal/tasks/expire-booking",
        {"booking_id": booking.id},
        settings.request_expiry_hours * 3600,
    )
    return booking


@router.post("", response_model=Booking, status_code=201)
def request_booking(
    body: BookingCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
    settings: Settings = Depends(get_settings),
):
    return create_booking_request(c, settings, uid, body)


@router.get("", response_model=list[Booking])
def my_bookings(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    bookings = c.bookings.for_user(uid)
    bookings.sort(key=lambda b: b.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return bookings


@router.get("/{booking_id}", response_model=Booking)
def get_booking(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    # Reveal the pickup address only once money has moved.
    if booking.state in (
        BookingState.CONFIRMED,
        BookingState.PICKED_UP,
        BookingState.RETURNED,
        BookingState.COMPLETED,
    ):
        booking.exact_address = c.listings.get_exact_address(booking.listing_id)
    return booking


@router.post("/{booking_id}/approve", response_model=Booking)
def approve(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    _transition_or_409(booking, BookingState.APPROVED, uid)

    borrower = c.users.get(booking.borrower_uid) or UserProfile(uid=booking.borrower_uid)
    customer_id = c.payments.ensure_customer(borrower.uid, borrower.stripe_customer_id)
    if customer_id != borrower.stripe_customer_id:
        borrower.stripe_customer_id = customer_id
        c.users.upsert(borrower)

    charge = c.payments.charge_rental(customer_id, booking.price.total_cents, booking.id)
    if charge.status not in ("succeeded", "requires_capture"):
        # Payment failed: stay APPROVED; client prompts borrower to fix payment.
        c.bookings.update(booking)
        raise HTTPException(status_code=402, detail="Payment failed; borrower must update payment method")
    booking.stripe_payment_intent = charge.id

    if booking.price.deposit_cents > 0:
        deposit = c.payments.hold_deposit(customer_id, booking.price.deposit_cents, booking.id)
        booking.stripe_deposit_intent = deposit.id

    _transition_or_409(booking, BookingState.CONFIRMED, "system", "payment captured")
    return c.bookings.update(booking)


@router.post("/{booking_id}/decline", response_model=Booking)
def decline(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    _transition_or_409(booking, BookingState.DECLINED, uid)
    return c.bookings.update(booking)


@router.post("/{booking_id}/cancel", response_model=Booking)
def cancel(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    was_paid = booking.state == BookingState.CONFIRMED
    to_state = (
        BookingState.CANCELLED_BY_BORROWER
        if uid == booking.borrower_uid
        else BookingState.CANCELLED_BY_LENDER
    )
    _transition_or_409(booking, to_state, uid)

    if was_paid and booking.stripe_payment_intent:
        if to_state == BookingState.CANCELLED_BY_LENDER:
            # Lender cancelled: borrower gets everything back including fee.
            c.payments.refund_rental(booking.stripe_payment_intent, None)
        else:
            # Borrower cancelled after paying: rental refunded, service fee kept.
            c.payments.refund_rental(
                booking.stripe_payment_intent, booking.price.rental_cents
            )
    if was_paid and booking.stripe_deposit_intent:
        c.payments.void_deposit(booking.stripe_deposit_intent)
    return c.bookings.update(booking)


@router.post("/{booking_id}/pickup", response_model=Booking)
def confirm_pickup(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Two-sided handoff: each party taps once; second tap flips the state."""
    booking = _get_booking_for(booking_id, uid, c)
    if booking.state != BookingState.CONFIRMED:
        raise HTTPException(status_code=409, detail=f"Cannot pick up from {booking.state.value}")
    if uid == booking.borrower_uid:
        booking.borrower_marked_pickup = True
    else:
        booking.lender_marked_pickup = True
    if booking.borrower_marked_pickup and booking.lender_marked_pickup:
        _transition_or_409(booking, BookingState.PICKED_UP, booking.lender_uid, "both confirmed")
    return c.bookings.update(booking)


@router.post("/{booking_id}/return", response_model=Booking)
def confirm_return(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Lender confirms the tool came back fine: release payout, void deposit."""
    booking = _get_booking_for(booking_id, uid, c)
    _transition_or_409(booking, BookingState.RETURNED, uid)

    lender = c.users.get(booking.lender_uid) or UserProfile(uid=booking.lender_uid)
    if lender.stripe_connect_id:
        booking.stripe_transfer_id = c.payments.payout_lender(
            lender.stripe_connect_id, booking.price.rental_cents, booking.id
        )
    # No Connect account yet: payout stays pending; lender onboards via
    # /v1/users/me/connect and a Cloud Task retries the transfer.

    if booking.stripe_deposit_intent:
        c.payments.void_deposit(booking.stripe_deposit_intent)

    _transition_or_409(booking, BookingState.COMPLETED, "system", "payout released")
    return c.bookings.update(booking)


class DisputeBody(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)
    capture_deposit_cents: int | None = Field(default=None, ge=0)


@router.post("/{booking_id}/dispute", response_model=Booking)
def dispute(
    booking_id: str,
    body: DisputeBody,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Lender reports damage instead of confirming a clean return.

    MVP policy: deposit (or the requested portion) is captured and held by the
    platform; the founder mediates manually and refunds/transfers from the
    dashboard. Rental payout is paused until resolution.
    """
    booking = _get_booking_for(booking_id, uid, c)
    if uid != booking.lender_uid:
        raise HTTPException(status_code=403, detail="Only the lender can open a dispute")
    if booking.state == BookingState.PICKED_UP:
        _transition_or_409(booking, BookingState.RETURNED, uid, "returned with dispute")
    _transition_or_409(booking, BookingState.DISPUTED, uid, body.reason)

    if booking.stripe_deposit_intent:
        amount = body.capture_deposit_cents or booking.price.deposit_cents
        amount = min(amount, booking.price.deposit_cents)
        if amount > 0:
            c.payments.capture_deposit(booking.stripe_deposit_intent, amount)
    return c.bookings.update(booking)
