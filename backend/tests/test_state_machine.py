from datetime import date

import pytest

from app.models import Booking, BookingState, PriceBreakdown
from app.state_machine import TransitionError, transition


def make_booking(state=BookingState.REQUESTED) -> Booking:
    return Booking(
        id="bkg_1",
        listing_id="lst_1",
        borrower_uid="b1",
        lender_uid="l1",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
        state=state,
        price=PriceBreakdown(
            days=2,
            price_per_day_cents=800,
            rental_cents=1600,
            service_fee_cents=240,
            total_cents=1840,
            deposit_cents=5000,
        ),
    )


def test_happy_path():
    b = make_booking()
    transition(b, BookingState.APPROVED, "l1")
    transition(b, BookingState.CONFIRMED, "system")
    transition(b, BookingState.PICKED_UP, "l1")
    transition(b, BookingState.RETURNED, "l1")
    transition(b, BookingState.COMPLETED, "system")
    assert b.state == BookingState.COMPLETED
    assert [e.to_state for e in b.timeline] == [
        BookingState.APPROVED,
        BookingState.CONFIRMED,
        BookingState.PICKED_UP,
        BookingState.RETURNED,
        BookingState.COMPLETED,
    ]


def test_borrower_cannot_approve_own_request():
    b = make_booking()
    with pytest.raises(TransitionError):
        transition(b, BookingState.APPROVED, "b1")


def test_stranger_cannot_touch_booking():
    b = make_booking()
    with pytest.raises(TransitionError):
        transition(b, BookingState.APPROVED, "someone_else")


def test_no_state_skipping():
    b = make_booking()
    with pytest.raises(TransitionError):
        transition(b, BookingState.COMPLETED, "system")
    with pytest.raises(TransitionError):
        transition(b, BookingState.PICKED_UP, "l1")


def test_idempotent_same_state_noop():
    b = make_booking(BookingState.CONFIRMED)
    before = len(b.timeline)
    transition(b, BookingState.CONFIRMED, "system")
    assert b.state == BookingState.CONFIRMED
    assert len(b.timeline) == before


def test_borrower_can_cancel_before_pickup_but_not_after():
    b = make_booking(BookingState.CONFIRMED)
    transition(b, BookingState.CANCELLED_BY_BORROWER, "b1")
    assert b.state == BookingState.CANCELLED_BY_BORROWER

    b2 = make_booking(BookingState.PICKED_UP)
    with pytest.raises(TransitionError):
        transition(b2, BookingState.CANCELLED_BY_BORROWER, "b1")


def test_expiry_only_from_requested():
    b = make_booking()
    transition(b, BookingState.EXPIRED, "system")
    assert b.state == BookingState.EXPIRED

    b2 = make_booking(BookingState.CONFIRMED)
    with pytest.raises(TransitionError):
        transition(b2, BookingState.EXPIRED, "system")


def test_dispute_flow():
    b = make_booking(BookingState.RETURNED)
    transition(b, BookingState.DISPUTED, "l1")
    transition(b, BookingState.COMPLETED, "system")
    assert b.state == BookingState.COMPLETED
