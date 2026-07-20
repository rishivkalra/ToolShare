"""Kit checkout, request expiry, payment setup, and payout sweep."""
from .conftest import add_card, auth


def _seed(client, title, price=800, owner="lender1"):
    resp = client.post(
        "/v1/listings",
        json={
            "title": title,
            "category": "power_tools",
            "price_per_day_cents": price,
            "lat": 37.7749,
            "lng": -122.4194,
        },
        headers=auth(owner),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Kit checkout
# ---------------------------------------------------------------------------

def test_kit_checkout_requests_all_tools(client, container):
    add_card(client, "borrower1")
    saw = _seed(client, "Circular saw", 800, "lender1")
    drill = _seed(client, "Cordless drill", 600, "lender2")

    resp = client.post(
        "/v1/projects/checkout",
        json={
            "listing_ids": [saw, drill],
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
        headers=auth("borrower1"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested"] == 2 and body["failed"] == 0
    assert all(i["booking_id"] for i in body["items"])

    # Each request got its own expiry task scheduled.
    expiry_tasks = [t for t in container.tasks.tasks if "expire" in t.path]
    assert len(expiry_tasks) == 2


def test_kit_checkout_partial_failure(client, listing, confirmed_booking):
    # `listing` already has a confirmed booking for Aug 1-2; a kit containing
    # it plus a free tool should succeed partially.
    free = _seed(client, "Palm sander", 500, "lender2")
    add_card(client, "borrower2")
    resp = client.post(
        "/v1/projects/checkout",
        json={
            "listing_ids": [listing["id"], free],
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
        headers=auth("borrower2"),
    )
    body = resp.json()
    assert body["requested"] == 1 and body["failed"] == 1
    failed = next(i for i in body["items"] if i["error"])
    assert failed["listing_id"] == listing["id"]
    assert "already booked" in failed["error"]


# ---------------------------------------------------------------------------
# Request expiry task
# ---------------------------------------------------------------------------

def test_expiry_task_expires_unanswered_request(client, container, listing):
    add_card(client, "borrower1")
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("borrower1"),
    )
    booking = resp.json()
    task = container.tasks.tasks[-1]
    assert task.path == "/internal/tasks/expire-booking"
    assert task.payload == {"booking_id": booking["id"]}

    # Simulate Cloud Tasks firing the callback.
    resp = client.post("/internal/tasks/expire-booking", json=task.payload)
    assert resp.json() == {"expired": True}
    resp = client.get(f"/v1/bookings/{booking['id']}", headers=auth("borrower1"))
    assert resp.json()["state"] == "expired"

    # Idempotent on redelivery.
    resp = client.post("/internal/tasks/expire-booking", json=task.payload)
    assert resp.json() == {"expired": False}


def test_expiry_task_leaves_confirmed_booking_alone(client, container, confirmed_booking):
    resp = client.post(
        "/internal/tasks/expire-booking", json={"booking_id": confirmed_booking["id"]}
    )
    assert resp.json() == {"expired": False}
    resp = client.get(f"/v1/bookings/{confirmed_booking['id']}", headers=auth("borrower1"))
    assert resp.json()["state"] == "confirmed"


# ---------------------------------------------------------------------------
# PaymentSheet setup intent
# ---------------------------------------------------------------------------

def test_setup_intent_creates_customer_and_secrets(client):
    resp = client.post("/v1/users/me/setup-intent", headers=auth("borrower1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == "cus_fake_borrower1"
    assert "secret" in body["setup_intent_client_secret"]
    assert body["ephemeral_key_secret"]

    # Customer id persisted on the profile for later off-session charges.
    resp = client.get("/v1/users/me", headers=auth("borrower1"))
    assert resp.json()["stripe_customer_id"] == "cus_fake_borrower1"


# ---------------------------------------------------------------------------
# Payout sweep after late Connect onboarding
# ---------------------------------------------------------------------------

def test_payout_sweep_pays_pending_completed_rentals(client, container, confirmed_booking):
    bid = confirmed_booking["id"]
    # Full handoff + return with NO Connect account: payout stays pending.
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("borrower1"))
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("lender1"))
    resp = client.post(f"/v1/bookings/{bid}/return", headers=auth("lender1"))
    assert resp.json()["state"] == "completed"
    assert resp.json()["stripe_transfer_id"] == ""
    assert container.payments.payouts == []

    # Lender onboards, app calls back: pending payout is swept.
    client.post("/v1/users/me/connect", headers=auth("lender1"))
    resp = client.post("/v1/users/me/connect/complete", headers=auth("lender1"))
    body = resp.json()
    assert body["paid_bookings"] == [bid]
    assert body["total_cents"] == confirmed_booking["price"]["rental_cents"]
    assert len(container.payments.payouts) == 1

    # Sweep is idempotent.
    resp = client.post("/v1/users/me/connect/complete", headers=auth("lender1"))
    assert resp.json()["paid_bookings"] == []


def test_payout_sweep_requires_onboarding_started(client):
    resp = client.post("/v1/users/me/connect/complete", headers=auth("nobody"))
    assert resp.status_code == 409
