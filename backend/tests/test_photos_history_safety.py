"""Photo upload, rental history tracking, card requirement, and reports."""
import io

from .conftest import add_card, auth


def test_photo_upload_and_serve(client, listing):
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"x" * 100
    resp = client.post(
        f"/v1/listings/{listing['id']}/photo",
        files={"file": ("saw.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        headers=auth("lender1"),
    )
    assert resp.status_code == 200, resp.text
    photos = resp.json()["photos"]
    assert len(photos) == 1 and photos[0].startswith("/v1/photos/")

    # Photo is publicly servable (dev store).
    resp = client.get(photos[0])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == fake_jpeg

    # Only the owner can attach photos.
    resp = client.post(
        f"/v1/listings/{listing['id']}/photo",
        files={"file": ("x.jpg", io.BytesIO(b"zz"), "image/jpeg")},
        headers=auth("someone_else"),
    )
    assert resp.status_code == 403

    # Non-images rejected.
    resp = client.post(
        f"/v1/listings/{listing['id']}/photo",
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
        headers=auth("lender1"),
    )
    assert resp.status_code == 400


def test_rental_history_tracks_days_and_renter(client, listing, confirmed_booking):
    # Give the borrower a display name so history shows a human name.
    client.patch("/v1/users/me", json={"display_name": "Maya R."}, headers=auth("borrower1"))

    resp = client.get(f"/v1/listings/{listing['id']}/history", headers=auth("lender1"))
    assert resp.status_code == 200, resp.text
    h = resp.json()
    assert h["times_rented"] == 1
    assert h["total_days_rented"] == 2          # Aug 1-2 inclusive
    assert h["total_earned_cents"] == 1600      # 2 days x $8, fee excluded
    assert h["active_borrower"] == "Maya R."    # confirmed booking = tool spoken for
    assert h["entries"][0]["borrower_name"] == "Maya R."
    assert h["entries"][0]["days"] == 2

    # History is owner-only.
    resp = client.get(f"/v1/listings/{listing['id']}/history", headers=auth("borrower1"))
    assert resp.status_code == 403


def test_card_required_before_booking(client, listing):
    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("cardless_carl"),
    )
    assert resp.status_code == 402
    assert "payment method" in resp.json()["detail"]

    add_card(client, "cardless_carl")
    resp = client.get("/v1/users/me", headers=auth("cardless_carl"))
    assert resp.json()["card_on_file"] is True
    assert resp.json()["card_last4"] == "4242"

    resp = client.post(
        "/v1/bookings",
        json={"listing_id": listing["id"], "start_date": "2026-08-01", "end_date": "2026-08-01"},
        headers=auth("cardless_carl"),
    )
    assert resp.status_code == 201


def test_report_listing(client, listing, container):
    resp = client.post(
        "/v1/reports",
        json={"target_type": "listing", "target_id": listing["id"],
              "reason": "Photos don't match the actual tool"},
        headers=auth("borrower1"),
    )
    assert resp.status_code == 201
    assert container.reports.reports[0].reporter_uid == "borrower1"


def test_profile_bio_update(client):
    resp = client.patch(
        "/v1/users/me",
        json={"display_name": "Raj P.", "bio": "Woodworker on Oak Ave. Happy to demo tools!"},
        headers=auth("raj"),
    )
    assert resp.status_code == 200
    assert resp.json()["bio"].startswith("Woodworker")
