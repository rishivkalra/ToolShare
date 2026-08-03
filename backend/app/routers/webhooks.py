"""Stripe webhook receiver.

Completes the async payment paths that the synchronous approve flow can't:
  payment_intent.succeeded (kind=rental)   3DS/async card confirmed after
                                           approval -> booking CONFIRMED
  identity.verification_session.verified   Stripe Identity passed -> profile
                                           id_verified badge

Signature scheme (Stripe-Signature: t=<ts>,v1=<hmac>): HMAC-SHA256 of
"<ts>.<raw body>" with the webhook signing secret. Handlers are idempotent —
replayed events find the state already applied and no-op.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import BookingState

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

_TOLERANCE_SECONDS = 300


def verify_stripe_signature(payload: bytes, header: str, secret: str) -> bool:
    parts = dict(
        p.split("=", 1) for p in header.split(",") if "=" in p
    )
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig:
        return False
    try:
        if abs(time.time() - int(ts)) > _TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    expected = hmac.new(
        secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    c: Container = Depends(get_container),
):
    payload = await request.body()
    secret = settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not verify_stripe_signature(
        payload, request.headers.get("Stripe-Signature", ""), secret
    ):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(payload)
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if etype == "payment_intent.succeeded":
        _handle_rental_paid(c, obj)
    elif etype == "payment_intent.payment_failed":
        _handle_rental_failed(c, obj)
    elif etype == "identity.verification_session.verified":
        _handle_identity_verified(c, obj)
    # Everything else: acknowledged and ignored.
    return {"received": True}


def _handle_rental_paid(c, obj: dict) -> None:
    meta = obj.get("metadata", {})
    if meta.get("kind") != "rental":
        return
    booking = c.bookings.get(meta.get("booking_id", ""))
    if not booking or booking.state != BookingState.APPROVED:
        return  # already confirmed synchronously, or unknown — idempotent no-op
    booking.stripe_payment_intent = obj.get("id", booking.stripe_payment_intent)
    # Run the exact same completion as the synchronous path: deposit hold,
    # CONFIRMED transition, referral bounty, borrower notification.
    from ..models import UserProfile
    from .bookings import finalize_confirmation

    borrower = c.users.get(booking.borrower_uid) or UserProfile(uid=booking.borrower_uid)
    customer_id = c.payments.ensure_customer(borrower.uid, borrower.stripe_customer_id)
    try:
        finalize_confirmation(c, booking, borrower, customer_id)
    except Exception:
        # Deposit hold failed: finalize already unwound charge + credit and
        # persisted APPROVED. Tell the borrower; webhook itself returns 200.
        c.notifier.notify(
            booking.borrower_uid,
            "Payment issue — update your card",
            f"The deposit hold for {booking.listing_title} didn't go through; "
            "your charge was refunded. Update your card and ask the owner to retry.",
            booking_id=booking.id,
        )


def _handle_rental_failed(c, obj: dict) -> None:
    meta = obj.get("metadata", {})
    if meta.get("kind") != "rental":
        return
    booking = c.bookings.get(meta.get("booking_id", ""))
    if not booking or booking.state != BookingState.APPROVED:
        return
    # Async charge died: hand back any reserved credit so it isn't stranded.
    from .bookings import release_pending_payment

    release_pending_payment(c, booking)
    c.bookings.update(booking)
    c.notifier.notify(
        booking.borrower_uid,
        "Payment failed — update your card",
        f"Your rental of {booking.listing_title} is approved but the charge "
        "didn't go through. Fix your payment method to confirm it.",
        booking_id=booking.id,
    )


def _handle_identity_verified(c, obj: dict) -> None:
    uid = obj.get("metadata", {}).get("uid", "")
    user = c.users.get(uid) if uid else None
    if user and not user.id_verified:
        user.id_verified = True
        c.users.upsert(user)
        c.notifier.notify(uid, "You're ID-verified 🪪", "Your trust badge is live.", kind="system")
