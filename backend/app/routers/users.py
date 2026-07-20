from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import current_uid
from ..deps import Container, get_container
from ..models import BookingState, Listing, UserProfile, UserUpdate

# A tool's purchase price ≈ this many daily rentals (shared heuristic).
BUY_MULTIPLE = 35

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
def me(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    user = c.users.get(uid)
    if not user:
        user = c.users.upsert(
            UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
        )
    return user


@router.patch("/me", response_model=UserProfile)
def update_me(
    body: UserUpdate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    return c.users.upsert(user)


class ConnectLinkResponse(BaseModel):
    connect_account_id: str
    onboarding_url: str


@router.post("/me/connect", response_model=ConnectLinkResponse)
def start_connect_onboarding(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Stripe Connect Express hosted onboarding so a lender can get paid.

    Triggered lazily — lenders can list tools first and onboard at their
    first approved booking.
    """
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    acct_id, url = c.payments.onboarding_link(uid, user.stripe_connect_id)
    if acct_id != user.stripe_connect_id:
        user.stripe_connect_id = acct_id
        c.users.upsert(user)
    return ConnectLinkResponse(connect_account_id=acct_id, onboarding_url=url)


class SetupIntentResponse(BaseModel):
    customer_id: str
    setup_intent_client_secret: str
    ephemeral_key_secret: str


@router.post("/me/setup-intent", response_model=SetupIntentResponse)
def create_setup_intent(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Everything the mobile Stripe PaymentSheet needs to save a card.

    Called before the first booking request; the saved payment method is then
    charged off-session when a lender approves.
    """
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    customer_id = c.payments.ensure_customer(uid, user.stripe_customer_id)
    if customer_id != user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        c.users.upsert(user)
    bundle = c.payments.create_setup_intent(customer_id)
    return SetupIntentResponse(
        customer_id=bundle.customer_id,
        setup_intent_client_secret=bundle.setup_intent_client_secret,
        ephemeral_key_secret=bundle.ephemeral_key_secret,
    )


class PaymentMethodStatus(BaseModel):
    card_on_file: bool
    card_last4: str


@router.post("/me/payment-method", response_model=PaymentMethodStatus)
def confirm_payment_method(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Called after the PaymentSheet saves a card: verifies with the payment
    provider and records card-on-file status. A card on file is required
    before any rental request — the safety anchor for both sides."""
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    customer_id = c.payments.ensure_customer(uid, user.stripe_customer_id)
    user.stripe_customer_id = customer_id
    last4 = c.payments.card_last4(customer_id)
    user.card_on_file = last4 is not None
    user.card_last4 = last4 or ""
    c.users.upsert(user)
    return PaymentMethodStatus(card_on_file=user.card_on_file, card_last4=user.card_last4)


class IdentitySessionResponse(BaseModel):
    verification_url: str  # "" when verified instantly (staging)
    id_verified: bool


@router.post("/me/identity-session", response_model=IdentitySessionResponse)
def start_identity_verification(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Top rung of the trust ladder: government-ID verification.

    Prod sends the user to Stripe Identity's hosted flow (the webhook flips
    the badge); staging verifies instantly so the ladder is fully testable.
    """
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    if user.id_verified:
        return IdentitySessionResponse(verification_url="", id_verified=True)
    session = c.identity.start(uid)
    if session.verified_now:
        user.id_verified = True
        c.users.upsert(user)
    return IdentitySessionResponse(
        verification_url=session.url, id_verified=user.id_verified
    )


class PayoutSweepResponse(BaseModel):
    paid_bookings: list[str]
    total_cents: int


@router.post("/me/connect/complete", response_model=PayoutSweepResponse)
def complete_connect_onboarding(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Called when the app returns from Stripe Connect hosted onboarding.

    Sweeps any completed rentals whose payout was pending because the lender
    had no Connect account at return time.
    """
    user = c.users.get(uid)
    if not user or not user.stripe_connect_id:
        raise HTTPException(status_code=409, detail="Connect onboarding not started")

    paid: list[str] = []
    total = 0
    for booking in c.bookings.for_user(uid):
        if (
            booking.lender_uid == uid
            and booking.state == BookingState.COMPLETED
            and not booking.stripe_transfer_id
        ):
            booking.stripe_transfer_id = c.payments.payout_lender(
                user.stripe_connect_id, booking.price.rental_cents, booking.id
            )
            c.bookings.update(booking)
            paid.append(booking.id)
            total += booking.price.rental_cents
    return PayoutSweepResponse(paid_bookings=paid, total_cents=total)


class Ledger(BaseModel):
    """The two numbers that keep both sides hooked: what borrowing saved you,
    and what lending earned you."""

    rentals_as_borrower: int
    spent_cents: int
    saved_vs_buying_cents: int
    rentals_as_lender: int
    earned_cents: int


_LEDGER_STATES = {BookingState.RETURNED, BookingState.COMPLETED}


@router.get("/me/ledger", response_model=Ledger)
def my_ledger(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    borrowed = spent = saved = lent = earned = 0
    for b in c.bookings.for_user(uid):
        if b.state not in _LEDGER_STATES:
            continue
        if b.borrower_uid == uid:
            borrowed += 1
            spent += b.price.total_cents
            saved += max(0, b.price.price_per_day_cents * BUY_MULTIPLE - b.price.rental_cents)
        if b.lender_uid == uid:
            lent += 1
            earned += b.price.rental_cents
    return Ledger(
        rentals_as_borrower=borrowed, spent_cents=spent,
        saved_vs_buying_cents=saved,
        rentals_as_lender=lent, earned_cents=earned,
    )


@router.get("/me/favorites", response_model=list[Listing])
def my_favorites(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    user = c.users.get(uid)
    if not user:
        return []
    out = []
    for lid in user.favorites:
        listing = c.listings.get(lid)
        if listing:
            out.append(listing)
    return out


@router.get("/{uid}", response_model=UserProfile)
def public_profile(uid: str, c: Container = Depends(get_container)):
    user = c.users.get(uid) or UserProfile(uid=uid)
    # Strip payment identifiers and contact info from public view.
    user.stripe_customer_id = ""
    user.stripe_connect_id = ""
    user.email = ""
    return user
