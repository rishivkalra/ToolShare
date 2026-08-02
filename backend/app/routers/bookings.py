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

from fastapi import APIRouter, Depends, HTTPException, UploadFile
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
    borrower = c.users.get(uid)
    if not borrower or not borrower.card_on_file:
        raise HTTPException(
            status_code=402,
            detail="Add a payment method before requesting a rental — it backs "
                   "the deposit hold that protects the tool owner.",
        )
    if c.bookings.overlapping(body.listing_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="Those dates are already booked")
    if any(body.start_date <= d <= body.end_date for d in listing.blackout_dates):
        raise HTTPException(status_code=409, detail="The owner has blocked some of those dates")

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
            listing.price_per_week_cents,
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
    borrower_name = borrower.display_name or uid

    # Instant book: ID-verified borrowers on instant-book listings skip the
    # approval wait — charge and confirm on the spot.
    if listing.instant_book and borrower.id_verified:
        _transition_or_409(booking, BookingState.APPROVED, booking.lender_uid, "instant book")
        booking = charge_and_confirm(c, booking)
        c.notifier.notify(
            booking.lender_uid,
            f"⚡ Instant booking — {borrower_name} rented your {listing.title}",
            f"{booking.start_date} → {booking.end_date} · "
            f"you earn ${booking.price.rental_cents / 100:.2f}. They're ID-verified.",
            booking_id=booking.id,
        )
        return booking

    c.tasks.schedule(
        "/internal/tasks/expire-booking",
        {"booking_id": booking.id},
        settings.request_expiry_hours * 3600,
    )
    c.notifier.notify(
        booking.lender_uid,
        f"{borrower_name} wants to rent your {listing.title}",
        f"{booking.start_date} → {booking.end_date} · "
        f"you'd earn ${booking.price.rental_cents / 100:.2f}. Respond within 24h.",
        booking_id=booking.id,
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


def charge_and_confirm(c: Container, booking: Booking) -> Booking:
    """APPROVED -> CONFIRMED: apply referral credit, charge the remainder,
    hold the deposit, pay the inviter's bounty on a first rental.

    Shared by lender approval and instant book. Raises 402 on payment failure
    (booking stays APPROVED so the borrower can fix their card).
    """
    borrower = c.users.get(booking.borrower_uid) or UserProfile(uid=booking.borrower_uid)
    customer_id = c.payments.ensure_customer(borrower.uid, borrower.stripe_customer_id)
    if customer_id != borrower.stripe_customer_id:
        borrower.stripe_customer_id = customer_id
        c.users.upsert(borrower)

    credit_used = min(borrower.credit_cents, booking.price.total_cents)
    to_charge = booking.price.total_cents - credit_used
    if to_charge > 0:
        charge = c.payments.charge_rental(customer_id, to_charge, booking.id)
        if charge.status not in ("succeeded", "requires_capture"):
            # Payment failed: stay APPROVED; borrower is told to fix payment.
            # Credit was not deducted — nothing to roll back.
            c.bookings.update(booking)
            raise HTTPException(status_code=402, detail="Payment failed; borrower must update payment method")
        booking.stripe_payment_intent = charge.id
    if credit_used:
        booking.credit_applied_cents = credit_used
        borrower.credit_cents -= credit_used
        c.users.upsert(borrower)

    if booking.price.deposit_cents > 0:
        try:
            deposit = c.payments.hold_deposit(customer_id, booking.price.deposit_cents, booking.id)
        except Exception:
            # Never keep money without a confirmed booking: unwind the charge,
            # persist the APPROVED state, surface a retryable failure.
            if booking.stripe_payment_intent:
                c.payments.refund_rental(booking.stripe_payment_intent, None)
                booking.stripe_payment_intent = ""
            c.bookings.update(booking)
            raise HTTPException(status_code=402, detail="Deposit hold failed; borrower must update payment method")
        booking.stripe_deposit_intent = deposit.id

    _transition_or_409(booking, BookingState.CONFIRMED, "system", "payment captured")

    # Referral bounty: the inviter is paid when the invited neighbor's FIRST
    # rental actually confirms — real usage, not signups.
    if borrower.referred_by and not borrower.referral_paid:
        referrer = c.users.get(borrower.referred_by)
        if referrer:
            referrer.credit_cents += 1000
            c.users.upsert(referrer)
            c.notifier.notify(
                referrer.uid,
                "Your invite paid off — $10 rental credit 🎉",
                f"{borrower.display_name or 'A neighbor you invited'} completed "
                "their first booking. Credit applies to your next rental.",
                kind="system",
            )
        borrower.referral_paid = True
        c.users.upsert(borrower)

    credit_note = (
        f" (${credit_used / 100:.2f} referral credit applied)" if credit_used else ""
    )
    c.notifier.notify(
        booking.borrower_uid,
        f"Confirmed! {booking.listing_title} is yours "
        f"{booking.start_date} → {booking.end_date}",
        f"You've been charged{credit_note}; the deposit is a hold, not a "
        "charge. Arrange pickup in chat.",
        booking_id=booking.id,
    )
    return c.bookings.update(booking)


@router.post("/{booking_id}/approve", response_model=Booking)
def approve(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    # Re-check overlap at approval time: two requests for the same dates can
    # both sit REQUESTED, but only one may be approved and charged.
    conflicts = [
        b for b in c.bookings.overlapping(
            booking.listing_id, booking.start_date, booking.end_date)
        if b.id != booking.id
    ]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail="Another booking already covers those dates — decline this one",
        )
    _transition_or_409(booking, BookingState.APPROVED, uid)
    return charge_and_confirm(c, booking)


@router.post("/{booking_id}/decline", response_model=Booking)
def decline(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = _get_booking_for(booking_id, uid, c)
    _transition_or_409(booking, BookingState.DECLINED, uid)
    c.notifier.notify(
        booking.borrower_uid,
        f"Request declined — {booking.listing_title}",
        "No charge was made. Similar tools may be available nearby.",
        booking_id=booking.id,
    )
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

    if was_paid:
        # Refund math must respect referral credit: cash refunds can never
        # exceed what was actually charged (total - credit), and the credit
        # portion comes back as credit, not cash.
        credit_used = booking.credit_applied_cents
        cash_charged = booking.price.total_cents - credit_used
        if to_state == BookingState.CANCELLED_BY_LENDER:
            # Lender cancelled: borrower is made completely whole.
            cash_refund = cash_charged
            credit_back = credit_used
        else:
            # Borrower cancelled: rental comes back, fees are kept. Credit is
            # treated as having paid the rental first.
            rental_credit = min(credit_used, booking.price.rental_cents)
            cash_refund = min(booking.price.rental_cents - rental_credit, cash_charged)
            credit_back = rental_credit
        if cash_refund > 0 and booking.stripe_payment_intent:
            c.payments.refund_rental(
                booking.stripe_payment_intent,
                None if cash_refund == cash_charged else cash_refund,
            )
        if credit_back > 0:
            borrower = c.users.get(booking.borrower_uid)
            if borrower:
                borrower.credit_cents += credit_back
                c.users.upsert(borrower)
            booking.credit_applied_cents -= credit_back
    if was_paid and booking.stripe_deposit_intent:
        c.payments.void_deposit(booking.stripe_deposit_intent)
    other = (
        booking.lender_uid if uid == booking.borrower_uid else booking.borrower_uid
    )
    c.notifier.notify(
        other,
        f"Booking cancelled — {booking.listing_title}",
        "Any payment was refunded per the cancellation policy.",
        booking_id=booking.id,
    )
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
        for party in (booking.borrower_uid, booking.lender_uid):
            c.notifier.notify(
                party,
                f"Handoff confirmed — {booking.listing_title}",
                f"Rental runs until {booking.end_date}. Day counter is live.",
                booking_id=booking.id,
            )
    else:
        other = (
            booking.lender_uid if uid == booking.borrower_uid else booking.borrower_uid
        )
        c.notifier.notify(
            other,
            f"Your neighbor confirmed the handoff — {booking.listing_title}",
            "Tap confirm on your side to start the rental.",
            booking_id=booking.id,
        )
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
    c.notifier.notify(
        booking.borrower_uid,
        f"Rental complete — {booking.listing_title}",
        "Deposit hold released. Leave your neighbor a review ⭐",
        booking_id=booking.id,
    )
    c.notifier.notify(
        booking.lender_uid,
        f"You earned ${booking.price.rental_cents / 100:.2f} 🎉",
        f"{booking.listing_title} came home safe. Payout is on its way.",
        booking_id=booking.id,
        kind="payout",
    )

    # Milestone: the moment a tool's lifetime earnings cross its rough
    # purchase price (~35 daily rentals), tell the owner it paid for itself.
    _EARNING = {BookingState.CONFIRMED, BookingState.PICKED_UP,
                BookingState.RETURNED, BookingState.COMPLETED, BookingState.DISPUTED}
    listing = c.listings.get(booking.listing_id)
    if listing:
        # by_listing includes this booking (PICKED_UP/COMPLETED both count).
        total = sum(
            b.price.rental_cents
            for b in c.bookings.by_listing(booking.listing_id)
            if b.state in _EARNING
        )
        payoff = listing.price_per_day_cents * 35
        if total >= payoff > total - booking.price.rental_cents:
            c.notifier.notify(
                booking.lender_uid,
                f"🏆 Your {listing.title} just paid for itself",
                f"Lifetime earnings hit ${total / 100:.0f} — everything from "
                "here is pure profit for a tool that was gathering dust.",
                kind="system",
            )
    return c.bookings.update(booking)


@router.post("/{booking_id}/photos", response_model=Booking)
async def handoff_photo(
    booking_id: str,
    phase: str,
    file: UploadFile,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Condition photos at pickup or return (either party, max 4 per phase).
    They anchor the AI damage check and any guarantee claim."""
    from ..services.photos import MAX_PHOTO_BYTES

    if phase not in ("pickup", "return"):
        raise HTTPException(status_code=400, detail="phase must be pickup or return")
    booking = _get_booking_for(booking_id, uid, c)
    if booking.state not in (BookingState.CONFIRMED, BookingState.PICKED_UP):
        raise HTTPException(status_code=409, detail="Photos are for active rentals")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only images are accepted")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large (max 5MB)")
    photos = booking.pickup_photos if phase == "pickup" else booking.return_photos
    if len(photos) >= 4:
        raise HTTPException(status_code=400, detail="Photo limit reached (4)")
    photos.append(c.photos.save(data, file.content_type))
    return c.bookings.update(booking)


class DamageCheckResponse(BaseModel):
    verdict: str
    notes: str


@router.post("/{booking_id}/damage-check", response_model=DamageCheckResponse)
def damage_check(
    booking_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """AI before/after comparison of the handoff photos — run it before
    confirming the return or opening a dispute."""
    booking = _get_booking_for(booking_id, uid, c)
    if not booking.pickup_photos or not booking.return_photos:
        raise HTTPException(
            status_code=409,
            detail="Need at least one pickup photo and one return photo first",
        )
    before = c.photos.load(booking.pickup_photos[-1])
    after = c.photos.load(booking.return_photos[-1])
    if not before or not after:
        raise HTTPException(status_code=502, detail="Couldn't load the photos")
    try:
        result = c.damage.compare(before[0], before[1], after[0], after[1])
    except Exception:
        raise HTTPException(status_code=502, detail="Condition check failed — try again")
    booking.damage_verdict = result.verdict
    booking.damage_notes = result.notes
    c.bookings.update(booking)
    return DamageCheckResponse(verdict=result.verdict, notes=result.notes)


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
    c.notifier.notify(
        booking.borrower_uid,
        f"Damage reported — {booking.listing_title}",
        "The owner opened a dispute; the deposit hold is retained while "
        "ToolShare reviews it. You're covered by the ToolShare Guarantee process.",
        booking_id=booking.id,
    )
    return c.bookings.update(booking)
