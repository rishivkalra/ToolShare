"""Rate limiting + founder console."""
import pytest

from .conftest import LISTING_BODY, add_card, auth


# ---------------- rate limiting ----------------

def test_listing_creation_rate_limited(client):
    for i in range(20):
        r = client.post("/v1/listings",
                        json=dict(LISTING_BODY, title=f"Drill number {i}"),
                        headers=auth("spammer"))
        assert r.status_code == 201
    r = client.post("/v1/listings", json=dict(LISTING_BODY, title="One too many"),
                    headers=auth("spammer"))
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "600"

    # Another identity is unaffected (per-user buckets).
    r = client.post("/v1/listings", json=dict(LISTING_BODY, title="Fine tool"),
                    headers=auth("honest"))
    assert r.status_code == 201


def test_ai_planner_rate_limited(client):
    body = {"description": "build a raised garden bed in my backyard",
            "lat": 37.7749, "lng": -122.4194}
    for _ in range(20):
        assert client.post("/v1/projects/plan", json=body,
                           headers=auth("burner")).status_code == 200
    assert client.post("/v1/projects/plan", json=body,
                       headers=auth("burner")).status_code == 429


# ---------------- founder console ----------------

@pytest.fixture()
def admin_env(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "admin_uids", "founder")


def _make_dispute(client, listing_id):
    add_card(client, "b1")
    bk = client.post("/v1/bookings", json={
        "listing_id": listing_id, "start_date": "2026-09-01", "end_date": "2026-09-02",
    }, headers=auth("b1")).json()
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth("b1"))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bk['id']}/dispute",
                json={"reason": "chipped blade on return"}, headers=auth("lender1"))
    return bk["id"]


def test_admin_gate(client, admin_env):
    assert client.get("/v1/admin/overview", headers=auth("rando")).status_code == 403
    assert client.get("/v1/admin/overview", headers=auth("founder")).status_code == 200


def test_admin_overview_lists_reports_and_disputes(client, admin_env, listing):
    client.post("/v1/reports",
                json={"target_type": "listing", "target_id": listing["id"],
                      "reason": "price gouging suspicion"},
                headers=auth("b9"))
    bid = _make_dispute(client, listing["id"])

    ov = client.get("/v1/admin/overview", headers=auth("founder")).json()
    assert any(r["reason"] == "price gouging suspicion" for r in ov["reports"])
    assert any(b["id"] == bid for b in ov["disputes"])


def test_resolve_refund_borrower(client, container, admin_env, listing):
    bid = _make_dispute(client, listing["id"])
    r = client.post(f"/v1/admin/disputes/{bid}/resolve",
                    json={"outcome": "refund_borrower", "note": "wear and tear"},
                    headers=auth("founder"))
    assert r.status_code == 200
    assert r.json()["state"] == "completed"
    b = container.bookings.get(bid)
    # Captured deposit refunded to the borrower.
    assert (b.stripe_deposit_intent, None) in container.payments.refunds
    feed = client.get("/v1/notifications", headers=auth("b1")).json()
    assert any("resolved in your favor" in n["title"] for n in feed["items"])
    # Non-admin can't resolve.
    assert client.post(f"/v1/admin/disputes/{bid}/resolve",
                       json={"outcome": "pay_lender"},
                       headers=auth("b1")).status_code == 403


def test_resolve_pay_lender(client, container, admin_env, listing):
    bid = _make_dispute(client, listing["id"])
    r = client.post(f"/v1/admin/disputes/{bid}/resolve",
                    json={"outcome": "pay_lender"}, headers=auth("founder"))
    assert r.status_code == 200
    b = container.bookings.get(bid)
    # Deposit NOT refunded; capture stands.
    assert (b.stripe_deposit_intent, None) not in container.payments.refunds
    feed = client.get("/v1/notifications", headers=auth("lender1")).json()
    assert any("resolved in your favor" in n["title"] for n in feed["items"])
