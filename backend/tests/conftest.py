import pytest
from fastapi.testclient import TestClient

from app import deps
from app.main import app


@pytest.fixture()
def client():
    deps.reset_container()
    with TestClient(app) as c:
        yield c
    deps.reset_container()


@pytest.fixture()
def container(client):
    return deps.get_container()


def auth(uid: str) -> dict:
    return {"Authorization": f"Bearer dev:{uid}"}


LISTING_BODY = {
    "title": "DeWalt circular saw",
    "category": "power_tools",
    "description": "7-1/4 inch, sharp blade",
    "price_per_day_cents": 800,
    "deposit_cents": 5000,
    "lat": 37.7749,
    "lng": -122.4194,
    "exact_address": "123 Alder St, San Francisco, CA",
}


@pytest.fixture()
def listing(client):
    resp = client.post("/v1/listings", json=LISTING_BODY, headers=auth("lender1"))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def confirmed_booking(client, listing):
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-02"},
        headers=auth("borrower1"),
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()
    resp = client.post(f"/v1/bookings/{booking['id']}/approve", headers=auth("lender1"))
    assert resp.status_code == 200, resp.text
    return resp.json()
