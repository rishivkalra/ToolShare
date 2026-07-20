"""Sprint 2: photo-to-listing, kit pages, neighborhoods, referrals,
wanted signals + digest, instant book."""
import io

from .conftest import LISTING_BODY, add_card, auth


# ---------------- photo-to-listing AI ----------------

def test_identify_tool_from_photo(client):
    r = client.post(
        "/v1/listings/identify",
        files={"file": ("tool.jpg", io.BytesIO(b"fakejpegbytes"), "image/jpeg")},
        headers=auth("maya"),
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["title"] == "Cordless drill"
    assert s["category"] == "power_tools"
    assert s["price_per_day_cents"] >= 500
    assert s["confidence"] > 0.5


def test_identify_rejects_non_image(client):
    r = client.post(
        "/v1/listings/identify",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth("maya"),
    )
    assert r.status_code == 400


# ---------------- kits: persistence + public page ----------------

def test_kit_saved_and_shareable(client, listing):
    r = client.post(
        "/v1/projects/plan",
        json={"description": "build a raised garden bed in my backyard",
              "lat": 37.7749, "lng": -122.4194},
        headers=auth("borrower1"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kit_id"].startswith("kit_")
    assert body["share_path"] == f"/kit/{body['kit_id']}"

    page = client.get(body["share_path"])
    assert page.status_code == 200
    assert "garden bed" in page.text
    assert "og:title" in page.text
    assert "Rent this kit" in page.text


def test_kit_page_404(client):
    r = client.get("/kit/kit_doesnotexist")
    assert r.status_code == 404


def test_kit_gaps_logged_as_wanted(client, container):
    # No listings at all -> every required tool is a gap.
    client.post(
        "/v1/projects/plan",
        json={"description": "paint the bedroom walls and ceiling",
              "lat": 37.7749, "lng": -122.4194},
        headers=auth("borrower1"),
    )
    assert any(s.source == "kit" for s in container.wanted.signals)


# ---------------- wanted: search misses + digest ----------------

def test_unmatched_search_logged_and_digested(client, container, listing):
    r = client.get("/v1/listings/search",
                   params={"lat": 37.7749, "lng": -122.4194, "q": "tile saw"})
    assert r.json() == []
    assert any(s.term == "tile saw" and s.source == "search"
               for s in container.wanted.signals)

    # Digest notifies the owner listing in the same neighborhood (lender1).
    r = client.post("/internal/tasks/wanted-digest")
    assert r.status_code == 200
    assert r.json()["owners_notified"] >= 1
    feed = client.get("/v1/notifications", headers=auth("lender1")).json()
    assert any("Wanted near you" in n["title"] for n in feed["items"])


# ---------------- neighborhoods ----------------

def test_neighborhood_stats(client, listing):
    r = client.get("/v1/neighborhoods", params={"lat": 37.7749, "lng": -122.4194})
    assert r.status_code == 200
    s = r.json()
    assert s["listings"] == 1
    assert s["lenders"] == 1
    assert s["unlocked"] is False
    assert s["unlock_target"] == 40

    page = client.get(s["page_path"])
    assert page.status_code == 200
    assert "tools listed" in page.text
    assert "of 40 tools" in page.text


# ---------------- referrals ----------------

def test_referral_credits_full_loop(client, container, listing):
    # Referrer signs in first (must exist for attribution).
    client.post("/v1/auth/google", json={"credential": "fake:1:ref@x.com:Referrer"})
    # New neighbor arrives through the invite link.
    r = client.post("/v1/auth/google",
                    json={"credential": "fake:2:new@x.com:Newbie", "ref": "g1"})
    token = r.json()["token"]
    hdr = {"Authorization": f"Bearer {token}"}
    me = client.get("/v1/users/me", headers=hdr).json()
    assert me["credit_cents"] == 1000
    assert me["referred_by"] == "g1"

    # First confirmed rental: credit applied to the charge, referrer paid.
    client.post("/v1/users/me/payment-method", headers=hdr)
    b = client.post("/v1/bookings",
                    json={"listing_id": listing["id"],
                          "start_date": "2026-08-01", "end_date": "2026-08-02"},
                    headers=hdr).json()
    r = client.post(f"/v1/bookings/{b['id']}/approve", headers=auth("lender1"))
    booking = r.json()
    assert booking["state"] == "confirmed"
    assert booking["credit_applied_cents"] == 1000
    # $19.90 total - $10 credit = $9.90 actually charged
    assert container.payments.charges[-1][1] == 990

    referrer = container.users.get("g1")
    assert referrer.credit_cents == 1000  # bounty paid
    assert container.users.get("g2").referral_paid is True


def test_no_self_or_repeat_referral(client, container):
    client.post("/v1/auth/google", json={"credential": "fake:7:a@x.com:A"})
    # Second sign-in with a ref must not re-credit an existing user.
    client.post("/v1/auth/google", json={"credential": "fake:7:a@x.com:A", "ref": "g1"})
    assert container.users.get("g7").credit_cents == 0


# ---------------- instant book ----------------

def test_instant_book_for_id_verified(client, container):
    body = dict(LISTING_BODY, instant_book=True)
    listing = client.post("/v1/listings", json=body, headers=auth("lender1")).json()
    assert listing["instant_book"] is True

    add_card(client, "verified_b")
    client.post("/v1/users/me/identity-session", headers=auth("verified_b"))
    r = client.post("/v1/bookings",
                    json={"listing_id": listing["id"],
                          "start_date": "2026-08-05", "end_date": "2026-08-06"},
                    headers=auth("verified_b"))
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "confirmed"  # no approval wait

    # Not ID-verified -> normal request flow even on instant listings.
    add_card(client, "unverified_b")
    r = client.post("/v1/bookings",
                    json={"listing_id": listing["id"],
                          "start_date": "2026-08-10", "end_date": "2026-08-11"},
                    headers=auth("unverified_b"))
    assert r.json()["state"] == "requested"
