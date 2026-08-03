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


class Achievement(BaseModel):
    key: str
    icon: str
    label: str
    detail: str


_DONE_STATES = {BookingState.RETURNED, BookingState.COMPLETED}


@router.get("/{uid}/badges", response_model=list[Achievement])
def achievements(uid: str, c: Container = Depends(get_container)):
    """Computed achievements (never stored, never stale): the Duolingo-style
    collectibles that make profiles feel like progress."""
    tools = c.listings.by_owner(uid)
    bookings = c.bookings.for_user(uid)
    lent = [b for b in bookings if b.lender_uid == uid and b.state in _DONE_STATES]
    borrowed = [b for b in bookings if b.borrower_uid == uid and b.state in _DONE_STATES]
    earned = sum(b.price.rental_cents for b in lent)
    user = c.users.get(uid)

    out: list[Achievement] = []
    if lent:
        out.append(Achievement(key="first_lend", icon="🤝", label="First lend",
                               detail="Completed a rental as an owner"))
    if len(tools) >= 5:
        out.append(Achievement(key="tool_hero", icon="🧰", label="Tool hero",
                               detail=f"{len(tools)} tools listed for the street"))
    if earned >= 10_000:
        out.append(Achievement(key="power_lender", icon="💰", label="Power lender",
                               detail=f"${earned / 100:.0f} earned from idle tools"))
    if len(borrowed) >= 3:
        out.append(Achievement(key="serial_borrower", icon="🔁", label="Serial borrower",
                               detail=f"{len(borrowed)} rentals instead of purchases"))
    if user and user.rating_count >= 5 and user.rating_avg >= 4.8:
        out.append(Achievement(key="five_star", icon="🌟", label="5-star neighbor",
                               detail=f"{user.rating_count} reviews averaging {user.rating_avg}"))
    avg_minutes, is_super = _responsiveness(c, uid)
    if is_super:
        out.append(Achievement(key="super_lender", icon="⚡", label="Super lender",
                               detail=f"Answers requests in ~{avg_minutes} min on average"))
    return out


def _responsiveness(c: Container, uid: str) -> tuple[int, bool]:
    """(avg minutes to answer a request, super-lender?) from booking
    timelines — the Airbnb-Superhost trust signal, computed not claimed.
    Needs ≥3 answered requests; Super Lender = averages under 2 hours."""
    waits = []
    for b in c.bookings.for_user(uid):
        if b.lender_uid != uid or not b.timeline:
            continue
        requested = next((e.at for e in b.timeline
                          if e.to_state == BookingState.REQUESTED), None)
        answered = next((e.at for e in b.timeline
                         if e.to_state in (BookingState.APPROVED, BookingState.DECLINED)
                         and e.actor_uid == uid), None)
        if requested and answered and answered >= requested:
            waits.append((answered - requested).total_seconds() / 60)
    if len(waits) < 3:
        return 0, False
    avg = int(sum(waits) / len(waits))
    return max(avg, 1), avg <= 120


@router.get("/{uid}", response_model=UserProfile)
def public_profile(uid: str, c: Container = Depends(get_container)):
    user = c.users.get(uid) or UserProfile(uid=uid)
    avg_minutes, is_super = _responsiveness(c, uid)
    # Whitelist, don't blacklist: rebuild the payload from only the fields a
    # stranger should see (trust badges + reputation). Everything else —
    # email, card digits, credit balance, referral graph, favorites, Stripe
    # ids — stays private by omission.
    return UserProfile(
        uid=user.uid,
        display_name=user.display_name,
        photo_url=user.photo_url,
        bio=user.bio,
        phone_verified=user.phone_verified,
        id_verified=user.id_verified,
        card_on_file=user.card_on_file,  # badge only; last4 never leaves
        rating_avg=user.rating_avg,
        rating_count=user.rating_count,
        avg_response_minutes=avg_minutes,
        super_lender=is_super,
        created_at=user.created_at,
    )
