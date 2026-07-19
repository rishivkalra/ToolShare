#!/usr/bin/env python
"""ToolShare local acceptance run.

Boots the API in dev mode (in-memory storage, fake payments — zero
credentials) and drives every product flow end to end over real HTTP:

  1. lenders list tools                7. two-sided pickup handoff
  2. borrower geo-search               8. return -> payout pending
  3. AI project kit plan               9. Connect onboarding -> payout sweep
  4. one-tap kit checkout             10. mutual reviews
  5. card setup (PaymentSheet data)   11. 24h request-expiry job
  6. approve -> charge + deposit      12. privacy: address hidden/revealed

Usage:  .venv/bin/python scripts/e2e_demo.py   (from backend/)
Exit code 0 = every step passed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

PORT = int(os.environ.get("DEMO_PORT", "8123"))
BASE = f"http://127.0.0.1:{PORT}"

PASSED: list[str] = []


def step(name: str, ok: bool, detail: str = ""):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        print("\nAcceptance run FAILED at:", name)
        sys.exit(1)
    PASSED.append(name)


def client_for(uid: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE,
        headers={"Authorization": f"Bearer dev:{uid}"},
        timeout=10,
    )


def main() -> None:
    print(f"\nToolShare local acceptance run  ->  {BASE}\n")

    lender1, lender2, borrower = client_for("lender1"), client_for("lender2"), client_for("borrower1")
    stranger = client_for("nosy_neighbor")

    # 1. Lenders list tools ---------------------------------------------------
    listings = {}
    for c, title, cat, price, deposit in [
        (lender1, "DeWalt circular saw", "power_tools", 800, 5000),
        (lender1, "Garden shovel", "garden", 500, 0),
        (lender2, "Cordless drill", "power_tools", 600, 2000),
        (lender2, "6ft step ladder", "ladders_access", 700, 0),
    ]:
        r = c.post(
            "/v1/listings",
            json={
                "title": title,
                "category": cat,
                "price_per_day_cents": price,
                "deposit_cents": deposit,
                "lat": 37.7749,
                "lng": -122.4194,
                "exact_address": "123 Alder St, San Francisco",
            },
        )
        assert r.status_code == 201, r.text
        listings[title] = r.json()["id"]
    step("Lenders list 4 tools", len(listings) == 4)

    # 2. Borrower geo-search --------------------------------------------------
    r = borrower.get("/v1/listings/search", params={"lat": 37.776, "lng": -122.418, "radius_km": 5})
    found = [x["listing"]["title"] for x in r.json()]
    step("Geo-search finds all nearby tools", len(found) == 4, ", ".join(sorted(found)))
    step("Public search never leaks exact addresses", "Alder" not in r.text)

    # 3. AI project kit -------------------------------------------------------
    r = borrower.post(
        "/v1/projects/plan",
        json={"description": "I want to build a raised garden bed in my backyard",
              "lat": 37.776, "lng": -122.418},
    )
    kit = r.json()
    matched = [i for i in kit["kit"] if i["matches"]]
    step(
        "Project kit: Claude plans tools, matched to neighbors",
        r.status_code == 200 and len(matched) >= 2,
        f"kit ${kit['total_estimated_per_day_cents'] / 100:.2f}/day, gaps: {kit['missing_tools'] or 'none'}",
    )

    # 4. One-tap kit checkout -------------------------------------------------
    kit_ids = [i["matches"][0]["id"] for i in matched]
    r = borrower.post(
        "/v1/projects/checkout",
        json={"listing_ids": kit_ids, "start_date": "2026-08-01", "end_date": "2026-08-02"},
    )
    checkout = r.json()
    step(
        "Kit checkout requests every tool in one tap",
        checkout["failed"] == 0 and checkout["requested"] == len(kit_ids),
        f"{checkout['requested']} booking requests created",
    )
    saw_booking = next(
        i["booking_id"] for i in checkout["items"] if i["listing_id"] == listings["DeWalt circular saw"]
    )

    # 5. Card setup (PaymentSheet inputs) ------------------------------------
    r = borrower.post("/v1/users/me/setup-intent")
    step(
        "PaymentSheet setup: customer + SetupIntent + ephemeral key",
        r.status_code == 200 and r.json()["setup_intent_client_secret"] != "",
    )

    # 6. Lender approves -> charge + deposit hold -----------------------------
    r = lender1.post(f"/v1/bookings/{saw_booking}/approve")
    b = r.json()
    step(
        "Approve charges rental+fee and holds deposit",
        b["state"] == "confirmed"
        and b["price"]["total_cents"] == 1840  # 2 days x $8 + 15% fee
        and b["stripe_deposit_intent"] != "",
        f"charged ${b['price']['total_cents'] / 100:.2f}, deposit hold ${b['price']['deposit_cents'] / 100:.2f}",
    )

    # 12a. Privacy: address revealed only to participants ---------------------
    r = borrower.get(f"/v1/bookings/{saw_booking}")
    step("Exact address revealed to borrower after payment", "Alder" in r.json()["exact_address"])
    r = stranger.get(f"/v1/bookings/{saw_booking}")
    step("Stranger cannot see the booking at all", r.status_code == 404)

    # chat --------------------------------------------------------------------
    borrower.post(f"/v1/bookings/{saw_booking}/messages", json={"text": "Hi! Porch pickup at 6pm ok?"})
    lender1.post(f"/v1/bookings/{saw_booking}/messages", json={"text": "Perfect, it'll be in the blue bin."})
    r = borrower.get(f"/v1/bookings/{saw_booking}/messages")
    step("Per-booking chat works both ways", len(r.json()) == 2)

    # 7. Two-sided pickup -----------------------------------------------------
    borrower.post(f"/v1/bookings/{saw_booking}/pickup")
    r = lender1.post(f"/v1/bookings/{saw_booking}/pickup")
    step("Two-sided handoff flips to picked_up", r.json()["state"] == "picked_up")

    # 8. Return with no Connect account -> payout pending ---------------------
    r = lender1.post(f"/v1/bookings/{saw_booking}/return")
    b = r.json()
    step(
        "Return completes rental; payout pending (no Connect yet)",
        b["state"] == "completed" and b["stripe_transfer_id"] == "",
    )

    # 9. Connect onboarding -> payout sweep -----------------------------------
    lender1.post("/v1/users/me/connect")
    r = lender1.post("/v1/users/me/connect/complete")
    sweep = r.json()
    step(
        "Connect onboarding sweeps pending payout to lender",
        sweep["paid_bookings"] == [saw_booking] and sweep["total_cents"] == 1600,
        f"lender paid ${sweep['total_cents'] / 100:.2f} (100% of list price)",
    )

    # 10. Mutual reviews ------------------------------------------------------
    borrower.post(f"/v1/bookings/{saw_booking}/reviews", json={"stars": 5, "text": "Great saw!"})
    lender1.post(f"/v1/bookings/{saw_booking}/reviews", json={"stars": 5, "text": "Returned spotless."})
    r = borrower.get("/v1/users/lender1")
    step("Mutual reviews update public ratings", r.json()["rating_avg"] == 5.0)

    # 11. Request-expiry job --------------------------------------------------
    r = borrower.post(
        "/v1/bookings",
        json={"listing_id": listings["6ft step ladder"], "start_date": "2026-09-01", "end_date": "2026-09-01"},
    )
    ladder_booking = r.json()["id"]
    r = httpx.post(f"{BASE}/internal/tasks/expire-booking", json={"booking_id": ladder_booking}, timeout=10)
    r2 = borrower.get(f"/v1/bookings/{ladder_booking}")
    step(
        "24h expiry job expires unanswered requests (idempotent)",
        r.json() == {"expired": True} and r2.json()["state"] == "expired",
    )

    print(f"\nAll {len(PASSED)} steps passed. The stack is ready for cloud deploy.\n")


if __name__ == "__main__":
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env={**os.environ, "TOOLSHARE_ENV": "dev"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            print("Server failed to start")
            sys.exit(1)
        main()
    finally:
        server.terminate()
        server.wait(timeout=5)
