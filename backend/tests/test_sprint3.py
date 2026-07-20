"""Sprint 3: guides, handoff photos + damage check, weekly pricing,
favorites, saved-search alerts, ledger, milestones."""
import io

from .conftest import LISTING_BODY, add_card, auth


def _book_and_confirm(client, listing_id, borrower="borrower1",
                      start="2026-08-01", end="2026-08-02"):
    add_card(client, borrower)
    b = client.post("/v1/bookings",
                    json={"listing_id": listing_id, "start_date": start, "end_date": end},
                    headers=auth(borrower)).json()
    client.post(f"/v1/bookings/{b['id']}/approve", headers=auth("lender1"))
    return b["id"]


# ---------------- build guides ----------------

def test_kit_guide_generated_and_cached(client, listing):
    kit = client.post(
        "/v1/projects/plan",
        json={"description": "build a raised garden bed in my backyard",
              "lat": 37.7749, "lng": -122.4194},
        headers=auth("borrower1"),
    ).json()
    r = client.post(f"/v1/projects/{kit['kit_id']}/guide", headers=auth("borrower1"))
    assert r.status_code == 200, r.text
    guide = r.json()
    assert guide["steps"] and guide["title"]
    # Cached: second call returns the same object.
    again = client.post(f"/v1/projects/{kit['kit_id']}/guide", headers=auth("borrower1"))
    assert again.json() == guide
    # Someone else's kit is off-limits.
    r = client.post(f"/v1/projects/{kit['kit_id']}/guide", headers=auth("other"))
    assert r.status_code == 403


# ---------------- handoff photos + damage check ----------------

def _img(name, data=b"samebytes"):
    return {"file": (name, io.BytesIO(data), "image/jpeg")}


def test_handoff_photos_and_damage_check(client, listing):
    bid = _book_and_confirm(client, listing["id"])

    # No photos yet -> 409.
    assert client.post(f"/v1/bookings/{bid}/damage-check",
                       headers=auth("lender1")).status_code == 409

    r = client.post(f"/v1/bookings/{bid}/photos?phase=pickup",
                    files=_img("before.jpg"), headers=auth("borrower1"))
    assert r.status_code == 200 and len(r.json()["pickup_photos"]) == 1
    client.post(f"/v1/bookings/{bid}/photos?phase=return",
                files=_img("after.jpg"), headers=auth("lender1"))

    # Identical bytes -> fake checker says ok.
    r = client.post(f"/v1/bookings/{bid}/damage-check", headers=auth("lender1"))
    assert r.json()["verdict"] == "ok"

    # A different return photo flips the verdict.
    client.post(f"/v1/bookings/{bid}/photos?phase=return",
                files=_img("after2.jpg", b"scratched!"), headers=auth("lender1"))
    r = client.post(f"/v1/bookings/{bid}/damage-check", headers=auth("lender1"))
    assert r.json()["verdict"] == "damage_suspected"

    b = client.get(f"/v1/bookings/{bid}", headers=auth("lender1")).json()
    assert b["damage_verdict"] == "damage_suspected"


def test_photo_phase_validated(client, listing):
    bid = _book_and_confirm(client, listing["id"])
    r = client.post(f"/v1/bookings/{bid}/photos?phase=nope",
                    files=_img("x.jpg"), headers=auth("borrower1"))
    assert r.status_code == 400


# ---------------- weekly pricing + suggestions ----------------

def test_weekly_rate_discounts_long_rentals(client):
    body = dict(LISTING_BODY, price_per_week_cents=4000)  # $40/wk vs $8/day
    listing = client.post("/v1/listings", json=body, headers=auth("lender1")).json()
    assert listing["price_per_week_cents"] == 4000

    add_card(client, "borrower1")
    b = client.post("/v1/bookings",
                    json={"listing_id": listing["id"],
                          "start_date": "2026-08-01", "end_date": "2026-08-09"},
                    headers=auth("borrower1")).json()
    # 9 days: 1 week ($40) + 2 days ($16) = $56 instead of $72.
    assert b["price"]["days"] == 9
    assert b["price"]["rental_cents"] == 5600


def test_price_suggestion(client, listing):
    r = client.get("/v1/listings/price-suggestion",
                   params={"category": "power_tools", "lat": 37.7749, "lng": -122.4194})
    s = r.json()
    assert s["suggested_per_day_cents"] >= 500
    r = client.get("/v1/listings/price-suggestion",
                   params={"category": "cleaning", "lat": 37.7749, "lng": -122.4194})
    assert r.json()["based_on"] == 0  # falls back to category default


# ---------------- favorites + saved searches ----------------

def test_favorites_roundtrip(client, listing):
    r = client.put(f"/v1/listings/{listing['id']}/favorite", headers=auth("maya"))
    assert r.json() == {"favorited": True, "count": 1}
    favs = client.get("/v1/users/me/favorites", headers=auth("maya")).json()
    assert favs[0]["id"] == listing["id"]
    r = client.put(f"/v1/listings/{listing['id']}/favorite", headers=auth("maya"))
    assert r.json()["favorited"] is False
    assert client.get("/v1/users/me/favorites", headers=auth("maya")).json() == []


def test_saved_search_alerts_on_new_listing(client):
    r = client.post("/v1/searches",
                    json={"term": "tile saw", "lat": 37.7749, "lng": -122.4194},
                    headers=auth("waiter"))
    assert r.status_code == 201

    body = dict(LISTING_BODY, title="Ryobi tile saw with tray")
    client.post("/v1/listings", json=body, headers=auth("lender1"))

    feed = client.get("/v1/notifications", headers=auth("waiter")).json()
    assert any("just listed" in n["title"] for n in feed["items"])

    # Idempotent create + delete.
    again = client.post("/v1/searches",
                        json={"term": "Tile Saw", "lat": 37.7749, "lng": -122.4194},
                        headers=auth("waiter")).json()
    mine = client.get("/v1/searches", headers=auth("waiter")).json()
    assert len(mine) == 1
    assert client.delete(f"/v1/searches/{again['id']}",
                         headers=auth("waiter")).status_code == 204


# ---------------- ledger + milestone ----------------

def test_ledger_after_completed_rental(client, listing):
    bid = _book_and_confirm(client, listing["id"])
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("borrower1"))
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bid}/return", headers=auth("lender1"))

    borrower = client.get("/v1/users/me/ledger", headers=auth("borrower1")).json()
    assert borrower["rentals_as_borrower"] == 1
    assert borrower["spent_cents"] == 1990
    # saved = 35*800 - 1600 = 26400
    assert borrower["saved_vs_buying_cents"] == 26400

    lender = client.get("/v1/users/me/ledger", headers=auth("lender1")).json()
    assert lender["rentals_as_lender"] == 1
    assert lender["earned_cents"] == 1600


def test_paid_for_itself_milestone(client):
    # $5/day tool: payoff at $175 lifetime. One 35-day rental crosses it.
    body = dict(LISTING_BODY, price_per_day_cents=500, deposit_cents=0)
    listing = client.post("/v1/listings", json=body, headers=auth("lender1")).json()
    bid = _book_and_confirm(client, listing["id"],
                            start="2026-08-01", end="2026-09-04")  # 35 days
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("borrower1"))
    client.post(f"/v1/bookings/{bid}/pickup", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bid}/return", headers=auth("lender1"))

    feed = client.get("/v1/notifications", headers=auth("lender1")).json()
    assert any("paid for itself" in n["title"] for n in feed["items"])
