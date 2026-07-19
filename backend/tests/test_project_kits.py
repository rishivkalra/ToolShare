"""Project-kit endpoint tests (FakePlanner + in-memory listings)."""
from .conftest import auth


def seed(client, title, category, price, lat=37.7749, lng=-122.4194, owner="lender1"):
    resp = client.post(
        "/v1/listings",
        json={
            "title": title,
            "category": category,
            "price_per_day_cents": price,
            "lat": lat,
            "lng": lng,
        },
        headers=auth(owner),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_project_kit_matches_nearby_tools(client):
    seed(client, "DeWalt circular saw", "power_tools", 800)
    seed(client, "Cordless drill", "power_tools", 600, owner="lender2")
    seed(client, "Garden shovel", "garden", 500, owner="lender3")

    resp = client.post(
        "/v1/projects/plan",
        json={
            "description": "I want to build a raised garden bed in my backyard",
            "lat": 37.776,
            "lng": -122.418,
        },
        headers=auth("borrower1"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    tool_names = [item["tool"]["name"] for item in body["kit"]]
    assert "circular saw" in tool_names
    assert "shovel" in tool_names

    saw_item = next(i for i in body["kit"] if i["tool"]["name"] == "circular saw")
    assert saw_item["matches"], "saw listing nearby should match"
    assert saw_item["matches"][0]["title"] == "DeWalt circular saw"

    # Kit total sums the cheapest match per required tool that has matches.
    assert body["total_estimated_per_day_cents"] > 0
    assert isinstance(body["missing_tools"], list)


def test_project_kit_reports_gaps_when_neighborhood_is_empty(client):
    resp = client.post(
        "/v1/projects/plan",
        json={
            "description": "Paint my living room walls and ceiling",
            "lat": 40.0,
            "lng": -100.0,
        },
        headers=auth("borrower1"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_estimated_per_day_cents"] == 0
    # Required tools with no nearby supply are surfaced as gaps.
    assert "paint roller kit" in body["missing_tools"]


def test_project_kit_requires_auth(client):
    resp = client.post(
        "/v1/projects/plan",
        json={"description": "Build a deck out back", "lat": 37.0, "lng": -122.0},
    )
    assert resp.status_code == 401
