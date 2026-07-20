"""Sprint 1: availability, notifications, ID verification, guarantee, webhooks."""
import hashlib
import hmac
import json
import time

from .conftest import add_card, auth


# ---------------- availability & blackouts ----------------

def test_availability_shows_booked_and_blackouts(client, listing):
    add_card(client, "borrower1")
    r = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    client.post(f"/v1/bookings/{r.json()['id']}/approve", headers=auth("lender1"))

    r = client.patch(
        f"/v1/listings/{listing['id']}",
        json={"blackout_dates": ["2026-08-10", "2026-08-11"]},
        headers=auth("lender1"),
    )
    assert r.status_code == 200

    avail = client.get(f"/v1/listings/{listing['id']}/availability").json()
    assert {"start_date": "2026-08-01", "end_date": "2026-08-02"} in avail["booked"]
    assert avail["blackout_dates"] == ["2026-08-10", "2026-08-11"]


def test_blackout_dates_block_bookings(client, listing):
    client.patch(
        f"/v1/listings/{listing['id']}",
        json={"blackout_dates": ["2026-09-02"]},
        headers=auth("lender1"),
    )
    add_card(client, "borrower1")
    r = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-09-01", "end_date": "2026-09-03"},
        headers=auth("borrower1"),
    )
    assert r.status_code == 409
    assert "blocked" in r.json()["detail"]


# ---------------- guarantee / protection fee ----------------

def test_protection_fee_in_breakdown(client, listing):
    add_card(client, "borrower1")
    r = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("borrower1"),
    )
    price = r.json()["price"]
    # 1 day x $8 = 800; fee max(120, 100) = 120; protection 150
    assert price["protection_fee_cents"] == 150
    assert price["total_cents"] == 800 + 120 + 150


# ---------------- notifications ----------------

def test_booking_lifecycle_emits_notifications(client, listing):
    add_card(client, "borrower1")
    r = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    bid = r.json()["id"]

    feed = client.get("/v1/notifications", headers=auth("lender1")).json()
    assert feed["unread"] == 1
    assert "wants to rent" in feed["items"][0]["title"]

    client.post(f"/v1/bookings/{bid}/approve", headers=auth("lender1"))
    feed = client.get("/v1/notifications", headers=auth("borrower1")).json()
    assert any("Confirmed" in n["title"] for n in feed["items"])

    client.post(f"/v1/bookings/{bid}/messages", json={"text": "porch pickup ok?"},
                headers=auth("borrower1"))
    feed = client.get("/v1/notifications", headers=auth("lender1")).json()
    assert any(n["kind"] == "message" for n in feed["items"])

    marked = client.post("/v1/notifications/read", headers=auth("lender1")).json()
    assert marked["marked"] >= 2
    assert client.get("/v1/notifications", headers=auth("lender1")).json()["unread"] == 0


def test_push_subscription_roundtrip(client, container):
    r = client.post(
        "/v1/notifications/subscriptions",
        json={"endpoint": "https://push.example/abc123", "p256dh": "keydata", "auth": "authdata"},
        headers=auth("maya"),
    )
    assert r.status_code == 201
    assert container.push_subs.for_user("maya")[0].endpoint == "https://push.example/abc123"
    assert client.get("/v1/notifications/config").json()["vapid_public_key"] == ""


# ---------------- identity verification ----------------

def test_identity_verification_ladder(client):
    me = client.get("/v1/users/me", headers=auth("maya")).json()
    assert me["id_verified"] is False
    r = client.post("/v1/users/me/identity-session", headers=auth("maya")).json()
    assert r["id_verified"] is True  # staging FakeIdentity verifies instantly
    assert client.get("/v1/users/me", headers=auth("maya")).json()["id_verified"] is True


# ---------------- stripe webhooks ----------------

SECRET = "whsec_test"


def _signed_headers(payload: bytes) -> dict:
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}"}


def test_webhook_confirms_async_payment(client, container, listing, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    add_card(client, "borrower1")
    r = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    bid = r.json()["id"]
    # Simulate the async-3DS path: approved but the charge confirms later.
    booking = container.bookings.get(bid)
    from app.models import BookingState
    booking.state = BookingState.APPROVED
    container.bookings.update(booking)

    payload = json.dumps({
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_async", "metadata": {"booking_id": bid, "kind": "rental"}}},
    }).encode()
    resp = client.post("/v1/webhooks/stripe", content=payload, headers=_signed_headers(payload))
    assert resp.status_code == 200
    assert container.bookings.get(bid).state == BookingState.CONFIRMED

    # Replay is idempotent.
    resp = client.post("/v1/webhooks/stripe", content=payload, headers=_signed_headers(payload))
    assert resp.status_code == 200
    assert container.bookings.get(bid).state == BookingState.CONFIRMED


def test_webhook_rejects_bad_signature(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    payload = b'{"type":"payment_intent.succeeded"}'
    r = client.post("/v1/webhooks/stripe", content=payload,
                    headers={"Stripe-Signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400


def test_webhook_identity_verified_event(client, container, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    client.get("/v1/users/me", headers=auth("raj"))  # create profile
    payload = json.dumps({
        "type": "identity.verification_session.verified",
        "data": {"object": {"metadata": {"uid": "raj"}}},
    }).encode()
    r = client.post("/v1/webhooks/stripe", content=payload, headers=_signed_headers(payload))
    assert r.status_code == 200
    assert container.users.get("raj").id_verified is True
