"""Flow-audit regressions: async 3DS payments end to end, pending-payment
credit release, dispute claim flow."""
import hashlib
import hmac
import json
import time

from .conftest import add_card, auth

SECRET = "whsec_test"


def _signed(payload: bytes) -> dict:
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}"}


def _request(client, listing_id, borrower="asyncb", start="2026-09-01", end="2026-09-02"):
    add_card(client, borrower)
    return client.post("/v1/bookings", json={
        "listing_id": listing_id, "start_date": start, "end_date": end,
    }, headers=auth(borrower)).json()


def _paid_event(bid):
    return json.dumps({
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_async_x",
                            "metadata": {"booking_id": bid, "kind": "rental"}}},
    }).encode()


def test_async_payment_full_flow(client, container, listing, monkeypatch):
    """3DS card: approve leaves APPROVED+pending; webhook completes with
    deposit hold, referral bounty and notification — same as sync."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)

    # Borrower arrived via referral and has credit.
    client.post("/v1/auth/google", json={"credential": "fake:1:r@x.com:Ref"})
    client.post("/v1/auth/google", json={"credential": "fake:2:n@x.com:New", "ref": "g1"})
    u = container.users.get("g2"); u.card_on_file = True; container.users.upsert(u)
    tok = client.post("/v1/auth/google", json={"credential": "fake:2:n@x.com:New"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-01", "end_date": "2026-09-02",
    }, headers=hdr).json()

    container.payments.next_charge_processing = True
    r = client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    assert r.status_code == 200
    b = container.bookings.get(bk["id"])
    assert b.state.value == "approved"          # waiting on the bank
    assert b.stripe_payment_intent.startswith("pi_async")
    assert b.credit_applied_cents == 1000       # reserved, not double-spendable
    assert container.users.get("g2").credit_cents == 0
    assert container.payments.deposits == []    # no deposit yet

    # Bank says yes -> webhook completes the exact same path as sync approval.
    resp = client.post("/v1/webhooks/stripe", content=_paid_event(bk["id"]),
                       headers=_signed(_paid_event(bk["id"])))
    assert resp.status_code == 200
    b = container.bookings.get(bk["id"])
    assert b.state.value == "confirmed"
    assert b.stripe_deposit_intent != ""        # deposit held (was missing before)
    assert container.users.get("g1").credit_cents == 1000  # referral bounty paid
    feed = client.get("/v1/notifications", headers=hdr).json()
    assert any("Confirmed!" in n["title"] for n in feed["items"])


def test_pending_cancel_releases_credit_and_intent(client, container, listing):
    client.post("/v1/auth/google", json={"credential": "fake:3:c@x.com:C"})
    u = container.users.get("g3"); u.card_on_file = True; u.credit_cents = 500
    container.users.upsert(u)
    tok = client.post("/v1/auth/google", json={"credential": "fake:3:c@x.com:C"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-05", "end_date": "2026-09-06",
    }, headers=hdr).json()
    container.payments.next_charge_processing = True
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    assert container.users.get("g3").credit_cents == 0

    client.post(f"/v1/bookings/{bk['id']}/cancel", headers=hdr)
    b = container.bookings.get(bk["id"])
    assert b.state.value == "cancelled_by_borrower"
    assert b.credit_applied_cents == 0
    assert b.stripe_payment_intent == ""
    assert container.users.get("g3").credit_cents == 500  # fully restored


def test_payment_failed_webhook_releases_credit(client, container, listing, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    client.post("/v1/auth/google", json={"credential": "fake:4:d@x.com:D"})
    u = container.users.get("g4"); u.card_on_file = True; u.credit_cents = 700
    container.users.upsert(u)
    tok = client.post("/v1/auth/google", json={"credential": "fake:4:d@x.com:D"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-08", "end_date": "2026-09-09",
    }, headers=hdr).json()
    container.payments.next_charge_processing = True
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))

    payload = json.dumps({
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_async_x",
                            "metadata": {"booking_id": bk["id"], "kind": "rental"}}},
    }).encode()
    client.post("/v1/webhooks/stripe", content=payload, headers=_signed(payload))
    assert container.users.get("g4").credit_cents == 700  # credit back
    assert container.bookings.get(bk["id"]).stripe_payment_intent == ""


def test_expire_pending_approved_releases_credit(client, container, listing):
    client.post("/v1/auth/google", json={"credential": "fake:5:e@x.com:E"})
    u = container.users.get("g5"); u.card_on_file = True; u.credit_cents = 300
    container.users.upsert(u)
    tok = client.post("/v1/auth/google", json={"credential": "fake:5:e@x.com:E"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-12", "end_date": "2026-09-13",
    }, headers=hdr).json()
    container.payments.next_charge_processing = True
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))

    r = client.post("/internal/tasks/expire-booking", json={"booking_id": bk["id"]})
    assert r.json() == {"expired": True}
    assert container.users.get("g5").credit_cents == 300


def test_dispute_flow_captures_deposit(client, container, listing):
    bk = _request(client, listing["id"])
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth("asyncb"))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth("lender1"))

    r = client.post(f"/v1/bookings/{bk['id']}/dispute",
                    json={"reason": "blade guard cracked on return"},
                    headers=auth("lender1"))
    assert r.status_code == 200
    assert r.json()["state"] == "disputed"
    # Deposit captured, not voided.
    assert len(container.payments.captured) == 1
    assert container.payments.voided == []
    # Borrower was told.
    feed = client.get("/v1/notifications", headers=auth("asyncb")).json()
    assert any("Damage reported" in n["title"] for n in feed["items"])
