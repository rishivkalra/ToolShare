#!/usr/bin/env bash
# Smoke test run from inside GCP (Cloud Build) against the deployed service.
# Requires: URL env var. Uses staging dev-auth tokens.
set -euo pipefail
H='Content-Type: application/json'
B='Authorization: Bearer dev:smoketest_borrower'
L='Authorization: Bearer dev:smoketest_lender'

echo "== healthz"
curl -sfS "$URL/health"; echo

echo "== create listing (Firestore write)"
LID=$(curl -sfS -X POST "$URL/v1/listings" -H "$L" -H "$H" -d '{
  "title":"Smoke test circular saw","category":"power_tools",
  "price_per_day_cents":800,"deposit_cents":5000,
  "lat":37.7749,"lng":-122.4194,"exact_address":"1 Test Way"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "listing: $LID"

echo "== geo search (Firestore geohash query)"
curl -sfS "$URL/v1/listings/search?lat=37.776&lng=-122.418&radius_km=5" \
  | python3 -c 'import sys,json;r=json.load(sys.stdin);print(len(r),"result(s):",[x["listing"]["title"] for x in r])'

echo "== card on file (required before booking)"
curl -sfS -X POST "$URL/v1/users/me/payment-method" -H "$B" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);assert d["card_on_file"];print("card:", d["card_last4"])'

echo "== booking request (state machine + Cloud Tasks expiry scheduling)"
BID=$(curl -sfS -X POST "$URL/v1/bookings" -H "$B" -H "$H" \
  -d "{\"listing_id\":\"$LID\",\"start_date\":\"2026-08-01\",\"end_date\":\"2026-08-02\"}" \
  | python3 -c 'import sys,json;b=json.load(sys.stdin);print(b["id"]);assert b["state"]=="requested";assert b["price"]["total_cents"]==1990')
echo "booking: $BID (requested, \$19.90)"

echo "== lender approves (staging FakePayments)"
curl -sfS -X POST "$URL/v1/bookings/$BID/approve" -H "$L" \
  | python3 -c 'import sys,json;b=json.load(sys.stdin);assert b["state"]=="confirmed",b;print("confirmed, deposit:",b["stripe_deposit_intent"])'

echo "== landing page served at /"
curl -sfS "$URL/" | grep -q "Borrow the tool" && echo "landing html ok"
curl -sfS -o /dev/null "$URL/app/landing.css" && echo "landing css ok"
curl -sfS -o /dev/null "$URL/app/landing.js" && echo "landing js ok"

echo "== auth config + session tokens"
curl -sfS "$URL/v1/auth/config" \
  | python3 -c 'import sys,json;c=json.load(sys.stdin);print("google:",c["google_client_id"] or "(not configured)","dev_auth:",c["dev_auth"])'
# Without a Google client id the endpoint must refuse cleanly (503), never 500.
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/v1/auth/google" -H "$H" -d '{"credential":"x"}')
[ "$CODE" = "503" ] || [ "$CODE" = "401" ] || { echo "unexpected auth status $CODE"; exit 1; }
echo "google sign-in endpoint: $CODE (expected while OAuth client unset)"

echo "== project kit plan + shareable kit page"
KITPATH=$(curl -sfS -X POST "$URL/v1/projects/plan" -H "$B" -H "$H" -d '{
  "description":"I want to build a raised garden bed in my backyard",
  "lat":37.776,"lng":-122.418}' \
  | python3 -c 'import sys,json;k=json.load(sys.stdin);print(k["share_path"]);import sys as s;print("kit tools:",[i["tool"]["name"] for i in k["kit"]],file=s.stderr)')
curl -sfS "$URL$KITPATH" | grep -q "Rent this kit" && echo "kit page ok: $KITPATH"

echo "== neighborhood stats + public scoreboard"
NPATH=$(curl -sfS "$URL/v1/neighborhoods?lat=37.776&lng=-122.418" \
  | python3 -c 'import sys,json;n=json.load(sys.stdin);print(n["page_path"]);import sys as s;print("listings:",n["listings"],"saved:",n["saved_cents"],file=s.stderr)')
curl -sfS "$URL$NPATH" | grep -q "tools listed" && echo "neighborhood page ok: $NPATH"

echo "== photo-to-listing identify (Gemini vision)"
python3 -c 'import base64,sys;sys.stdout.buffer.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))' > /tmp/px.png
curl -sfS -X POST "$URL/v1/listings/identify" -H "$L" -F "file=@/tmp/px.png;type=image/png" \
  | python3 -c 'import sys,json;s=json.load(sys.stdin);print("identified:",s["title"],f"(confidence {s[\"confidence\"]})")'

echo "SMOKE-OK"
