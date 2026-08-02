"""End-to-end audit regressions: privacy, money math, double-booking,
stuck states, deposit rollback, wanted-signal spam."""
from .conftest import LISTING_BODY, add_card, auth


# ---- A. public profile must not leak private fields ----

def test_public_profile_is_whitelisted(client, container):
    add_card(client, "victim")
    client.post("/v1/auth/google", json={"credential": "fake:9:inv@x.com:Inv"})
    client.post("/v1/auth/google",
                json={"credential": "fake:10:v@x.com:V", "ref": "g9"})
    client.put  # noqa - keep flow obvious

    pub = client.get("/v1/users/victim").json()
    assert pub["card_last4"] == ""
    assert pub["email"] == ""
    assert pub["stripe_customer_id"] == ""
    pub2 = client.get("/v1/users/g10").json()
    assert pub2["credit_cents"] == 0
    assert pub2["referred_by"] == ""
    assert pub2["favorites"] == []
    # Trust badges stay public.
    assert pub["card_on_file"] is True


# ---- C. approve re-checks overlap ----

def test_second_overlapping_approval_rejected(client, container, listing):
    add_card(client, "b1")
    add_card(client, "b2")
    bk1 = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-01", "end_date": "2026-09-03",
    }, headers=auth("b1")).json()
    bk2 = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-02", "end_date": "2026-09-04",
    }, headers=auth("b2")).json()

    assert client.post(f"/v1/bookings/{bk1['id']}/approve",
                       headers=auth("lender1")).status_code == 200
    r = client.post(f"/v1/bookings/{bk2['id']}/approve", headers=auth("lender1"))
    assert r.status_code == 409
    assert "already covers those dates" in r.json()["detail"]
    # Only one charge happened.
    assert len(container.payments.charges) == 1


# ---- B. cancellation with referral credit ----

def _credit_booking(client, container, listing, credit=1000):
    client.post("/v1/auth/google", json={"credential": "fake:20:c@x.com:C"})
    u = container.users.get("g20")
    u.credit_cents = credit
    u.card_on_file = True
    container.users.upsert(u)
    tok = client.post("/v1/auth/google",
                      json={"credential": "fake:20:c@x.com:C"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-10-01", "end_date": "2026-10-01",
    }, headers=hdr).json()
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    return bk["id"], hdr


def test_borrower_cancel_restores_credit_and_caps_cash_refund(client, container, listing):
    # total = 800 + 120 + 150 = 1070; credit 1000 -> cash charged 70
    bid, hdr = _credit_booking(client, container, listing)
    booking = container.bookings.get(bid)
    assert booking.credit_applied_cents == 1000
    assert container.payments.charges[-1][1] == 70

    client.post(f"/v1/bookings/{bid}/cancel", headers=hdr)
    # Rental (800) was fully covered by credit -> credit back, zero cash refund.
    assert container.payments.refunds == []
    assert container.users.get("g20").credit_cents == 800
    assert container.bookings.get(bid).credit_applied_cents == 200  # kept fees


def test_lender_cancel_makes_borrower_whole(client, container, listing):
    bid, _ = _credit_booking(client, container, listing)
    client.post(f"/v1/bookings/{bid}/cancel", headers=auth("lender1"))
    # Full cash refund of what was actually charged + all credit restored.
    assert container.payments.refunds[-1] == (container.payments.charges[-1][0], None)
    assert container.users.get("g20").credit_cents == 1000
    assert container.bookings.get(bid).credit_applied_cents == 0


# ---- D. failed-payment APPROVED bookings expire and free the dates ----

def test_stuck_approved_booking_expires(client, container, listing):
    add_card(client, "b1")
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-10", "end_date": "2026-09-11",
    }, headers=auth("b1")).json()
    container.payments.fail_next_charge = True
    r = client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    assert r.status_code == 402
    assert container.bookings.get(bk["id"]).state.value == "approved"

    # The 24h task now clears it instead of leaving the dates blocked forever.
    r = client.post("/internal/tasks/expire-booking", json={"booking_id": bk["id"]})
    assert r.json() == {"expired": True}
    assert container.bookings.get(bk["id"]).state.value == "expired"

    # Dates are bookable again.
    add_card(client, "b2")
    r = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-10", "end_date": "2026-09-11",
    }, headers=auth("b2"))
    assert r.status_code == 201


# ---- G. deposit-hold failure unwinds the charge ----

def test_deposit_failure_refunds_charge(client, container, listing):
    add_card(client, "b1")
    bk = client.post("/v1/bookings", json={
        "listing_id": listing["id"], "start_date": "2026-09-20", "end_date": "2026-09-21",
    }, headers=auth("b1")).json()
    container.payments.fail_next_deposit = True
    r = client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    assert r.status_code == 402
    assert "Deposit hold failed" in r.json()["detail"]
    # Charge was made then fully refunded; booking retryable at APPROVED.
    assert container.payments.refunds[-1][1] is None
    b = container.bookings.get(bk["id"])
    assert b.state.value == "approved"
    assert b.stripe_payment_intent == ""


# ---- E. wanted signals deduped per term/day ----

def test_search_miss_logged_once_per_day(client, container):
    for _ in range(5):
        client.get("/v1/listings/search",
                   params={"lat": 37.7749, "lng": -122.4194, "q": "tile saw"})
    assert len([s for s in container.wanted.signals if s.term == "tile saw"]) == 1
