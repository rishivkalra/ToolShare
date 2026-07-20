"""End-to-end API tests for the money loop, using in-memory repos + FakePayments."""
from .conftest import add_card, auth


def test_full_rental_happy_path(client, container, listing):
    # Borrower searches and finds the saw nearby.
    resp = client.get(
        "/v1/listings/search",
        params={"lat": 37.776, "lng": -122.418, "radius_km": 5},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["listing"]["title"] == "DeWalt circular saw"
    assert results[0]["distance_km"] <= 5

    # Public listing must not leak the exact address anywhere.
    assert "123 Alder" not in resp.text

    # A card on file is required before any request (safety guard).
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    assert resp.status_code == 402
    add_card(client, "borrower1")

    # Request 2 days: 2 x $8 = $16 rental + 15% fee ($2.40) = $18.40.
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    assert resp.status_code == 201
    booking = resp.json()
    assert booking["state"] == "requested"
    assert booking["price"]["rental_cents"] == 1600
    assert booking["price"]["service_fee_cents"] == 240
    assert booking["price"]["protection_fee_cents"] == 150  # ToolShare Guarantee
    assert booking["price"]["total_cents"] == 1990

    # Lender approves -> charge + deposit hold -> CONFIRMED.
    resp = client.post(f"/v1/bookings/{booking['id']}/approve", headers=auth("lender1"))
    assert resp.status_code == 200
    assert resp.json()["state"] == "confirmed"
    assert container.payments.charges[0][1] == 1990
    assert container.payments.deposits[0][1] == 5000

    # Address is now revealed to the borrower.
    resp = client.get(f"/v1/bookings/{booking['id']}", headers=auth("borrower1"))
    assert resp.json()["exact_address"] == "123 Alder St, San Francisco, CA"

    # But never to a stranger.
    resp = client.get(f"/v1/bookings/{booking['id']}", headers=auth("rando"))
    assert resp.status_code == 404

    # Two-sided pickup.
    client.post(f"/v1/bookings/{booking['id']}/pickup", headers=auth("borrower1"))
    resp = client.post(f"/v1/bookings/{booking['id']}/pickup", headers=auth("lender1"))
    assert resp.json()["state"] == "picked_up"

    # Lender needs a Connect account to be paid; onboard now.
    resp = client.post("/v1/users/me/connect", headers=auth("lender1"))
    assert resp.status_code == 200

    # Clean return: payout to lender (rental only, not the fee), deposit voided.
    resp = client.post(f"/v1/bookings/{booking['id']}/return", headers=auth("lender1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "completed"
    assert container.payments.payouts[0][1] == 1600
    assert container.payments.voided == [booking_deposit_id(container)]

    # Mutual reviews.
    resp = client.post(
        f"/v1/bookings/{booking['id']}/reviews",
        json={"stars": 5, "text": "Great saw, great neighbor"},
        headers=auth("borrower1"),
    )
    assert resp.status_code == 201
    resp = client.get("/v1/users/lender1", headers=auth("borrower1"))
    assert resp.json()["rating_avg"] == 5.0


def booking_deposit_id(container):
    return container.payments.deposits[0][0]


def test_cannot_book_own_listing(client, listing):
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("lender1"),
    )
    assert resp.status_code == 400


def test_double_booking_rejected(client, listing, confirmed_booking):
    add_card(client, "borrower2")
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-02", "end_date": "2026-08-03"},
        headers=auth("borrower2"),
    )
    assert resp.status_code == 409


def test_payment_failure_keeps_booking_approvable(client, container, listing):
    add_card(client, "borrower1")
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-09-01", "end_date": "2026-09-01"},
        headers=auth("borrower1"),
    )
    booking = resp.json()
    container.payments.fail_next_charge = True
    resp = client.post(f"/v1/bookings/{booking['id']}/approve", headers=auth("lender1"))
    assert resp.status_code == 402
    # Booking is APPROVED but not CONFIRMED; no deposit was held.
    resp = client.get(f"/v1/bookings/{booking['id']}", headers=auth("lender1"))
    assert resp.json()["state"] == "approved"
    assert container.payments.deposits == []


def test_lender_cancel_refunds_everything(client, container, confirmed_booking):
    resp = client.post(
        f"/v1/bookings/{confirmed_booking['id']}/cancel", headers=auth("lender1")
    )
    assert resp.json()["state"] == "cancelled_by_lender"
    # Full refund (None = full amount) and deposit void.
    assert container.payments.refunds == [(confirmed_booking["stripe_payment_intent"], None)]
    assert len(container.payments.voided) == 1


def test_borrower_cancel_keeps_service_fee(client, container, confirmed_booking):
    resp = client.post(
        f"/v1/bookings/{confirmed_booking['id']}/cancel", headers=auth("borrower1")
    )
    assert resp.json()["state"] == "cancelled_by_borrower"
    pid, amount = container.payments.refunds[0]
    assert amount == confirmed_booking["price"]["rental_cents"]  # fee not refunded


def test_dispute_captures_deposit(client, container, confirmed_booking):
    bid = confirmed_booking["id"]
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("borrower1"))
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("lender1"))
    resp = client.post(
        f"/v1/bookings/{bid}/dispute",
        json={"reason": "Blade came back chipped", "capture_deposit_cents": 2000},
        headers=auth("lender1"),
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "disputed"
    assert container.payments.captured == [(confirmed_booking["stripe_deposit_intent"], 2000)]


def test_min_service_fee_applies(client, listing):
    # 1 day at $8 -> fee would be $1.20; floor is $1.00 so pct applies.
    # Verify with a cheap listing where 15% < $1.
    body = {
        "title": "Screwdriver set",
        "category": "hand_tools",
        "price_per_day_cents": 500,
        "lat": 37.7749,
        "lng": -122.4194,
    }
    resp = client.post("/v1/listings", json=body, headers=auth("lender2"))
    lid = resp.json()["id"]
    add_card(client, "borrower1")
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": lid, "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("borrower1"),
    )
    price = resp.json()["price"]
    assert price["rental_cents"] == 500
    assert price["service_fee_cents"] == 100  # $1 floor beats 15% ($0.75)


def test_auth_required(client):
    assert client.get("/v1/listings/mine").status_code == 401
    assert client.get("/v1/bookings").status_code == 401
