"""Sticky layer: pulse feed, Super Lender responsiveness, achievements,
project wall."""
import io
from datetime import date, timedelta

from .conftest import LISTING_BODY, add_card, auth

LOC = {"lat": 37.7749, "lng": -122.4194}


def _complete_rental(client, listing_id, borrower="b1",
                     start=None, end=None):
    start = start or (date.today() + timedelta(days=1)).isoformat()
    end = end or start
    add_card(client, borrower)
    bk = client.post("/v1/bookings", json={
        "listing_id": listing_id, "start_date": start, "end_date": end,
    }, headers=auth(borrower)).json()
    client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth(borrower))
    client.post(f"/v1/bookings/{bk['id']}/pickup", headers=auth("lender1"))
    client.post(f"/v1/bookings/{bk['id']}/return", headers=auth("lender1"))
    return bk["id"]


# ---------------- pulse ----------------

def test_pulse_shows_listings_and_completions(client, listing):
    client.patch("/v1/users/me", json={"display_name": "Maya R."}, headers=auth("lender1"))
    _complete_rental(client, listing["id"])

    p = client.get("/v1/neighborhoods/pulse", params=LOC).json()
    texts = " | ".join(e["text"] for e in p["events"])
    assert "listed a DeWalt circular saw" in texts
    assert "borrowed the DeWalt circular saw" in texts
    assert "Maya R." in texts
    assert p["saved_this_week_cents"] > 0


# ---------------- responsiveness / super lender ----------------

def test_super_lender_computed_from_response_times(client, listing):
    # Three instant approvals (test-time gap ≈ seconds) -> super lender.
    for i in range(3):
        start = (date.today() + timedelta(days=10 + i * 3)).isoformat()
        add_card(client, f"rb{i}")
        bk = client.post("/v1/bookings", json={
            "listing_id": listing["id"], "start_date": start, "end_date": start,
        }, headers=auth(f"rb{i}")).json()
        client.post(f"/v1/bookings/{bk['id']}/approve", headers=auth("lender1"))

    pub = client.get("/v1/users/lender1").json()
    assert pub["super_lender"] is True
    assert pub["avg_response_minutes"] >= 1

    # A lender with no answered requests shows nothing.
    assert client.get("/v1/users/nobody").json()["super_lender"] is False


# ---------------- achievements ----------------

def test_achievements_computed(client, listing):
    _complete_rental(client, listing["id"])
    badges = client.get("/v1/users/lender1/badges").json()
    keys = {b["key"] for b in badges}
    assert "first_lend" in keys

    for i in range(3):
        start = (date.today() + timedelta(days=20 + i * 3)).isoformat()
        _complete_rental(client, listing["id"], borrower="serial", start=start)
    badges = client.get("/v1/users/serial/badges").json()
    assert "serial_borrower" in {b["key"] for b in badges}


# ---------------- project wall ----------------

def test_wall_gated_on_completed_rental(client, listing):
    form = {"caption": "Garden bed done in a weekend!", "lat": "37.7749", "lng": "-122.4194"}
    r = client.post("/v1/posts", data=form, headers=auth("stranger"))
    assert r.status_code == 403

    _complete_rental(client, listing["id"], borrower="builder")
    r = client.post(
        "/v1/posts", data=form,
        files={"file": ("build.jpg", io.BytesIO(b"jpegbytes"), "image/jpeg")},
        headers=auth("builder"),
    )
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["photo_url"]
    assert post["caption"].startswith("Garden bed")

    wall = client.get("/v1/posts", params=LOC).json()
    assert wall[0]["id"] == post["id"]

    # The public scoreboard page shows the wall + pulse.
    page = client.get("/n/9q8yy").text
    assert "Built nearby with borrowed tools" in page
    assert "Garden bed done in a weekend!" in page
    assert "This week on your streets" in page
