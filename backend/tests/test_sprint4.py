"""Sprint 4: live availability on search results, pause/reactivate."""
from datetime import date, timedelta

from .conftest import LISTING_BODY, add_card, auth

SEARCH = {"lat": 37.7749, "lng": -122.4194}


def test_search_shows_rented_until(client, listing):
    add_card(client, "borrower1")
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=2)).isoformat()
    b = client.post("/v1/bookings",
                    json={"listing_id": listing["id"], "start_date": start, "end_date": end},
                    headers=auth("borrower1")).json()

    r = client.get("/v1/listings/search", params=SEARCH).json()
    assert r[0]["rented_until"] is None  # requested only — not blocking yet

    client.post(f"/v1/bookings/{b['id']}/approve", headers=auth("lender1"))
    r = client.get("/v1/listings/search", params=SEARCH).json()
    assert r[0]["rented_until"] == end  # confirmed rental covering today


def test_future_booking_not_marked_rented(client, listing):
    add_card(client, "borrower1")
    start = (date.today() + timedelta(days=10)).isoformat()
    end = (date.today() + timedelta(days=12)).isoformat()
    b = client.post("/v1/bookings",
                    json={"listing_id": listing["id"], "start_date": start, "end_date": end},
                    headers=auth("borrower1")).json()
    client.post(f"/v1/bookings/{b['id']}/approve", headers=auth("lender1"))

    r = client.get("/v1/listings/search", params=SEARCH).json()
    assert r[0]["rented_until"] is None  # not out *today*


def test_paused_listing_hidden_from_search(client, listing):
    r = client.patch(f"/v1/listings/{listing['id']}", json={"status": "paused"},
                     headers=auth("lender1"))
    assert r.status_code == 200
    assert client.get("/v1/listings/search", params=SEARCH).json() == []

    client.patch(f"/v1/listings/{listing['id']}", json={"status": "active"},
                 headers=auth("lender1"))
    assert len(client.get("/v1/listings/search", params=SEARCH).json()) == 1
