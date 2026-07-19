# ToolShare Backend

FastAPI service implementing the full rental money loop: listings with geo
search, the booking state machine, Stripe charges/deposit holds/payouts, chat,
and reviews.

## Run locally (no credentials needed)

```bash
cd backend
uv venv .venv && uv pip install -p .venv/bin/python -r requirements.txt
TOOLSHARE_ENV=dev .venv/bin/uvicorn app.main:app --reload --port 8080
```

Dev mode uses in-memory storage and a fake payment provider, and accepts
`Authorization: Bearer dev:<any-uid>` so you can exercise every endpoint:

```bash
# lender lists a saw
curl -s -X POST localhost:8080/v1/listings \
  -H 'Authorization: Bearer dev:lender1' -H 'Content-Type: application/json' \
  -d '{"title":"Circular saw","category":"power_tools","price_per_day_cents":800,
       "deposit_cents":5000,"lat":37.77,"lng":-122.42,"exact_address":"123 Alder St"}'

# borrower books it
curl -s -X POST localhost:8080/v1/bookings \
  -H 'Authorization: Bearer dev:borrower1' -H 'Content-Type: application/json' \
  -d '{"listing_id":"lst_000001","start_date":"2026-08-01","end_date":"2026-08-02"}'

# lender approves (charges borrower, holds deposit)
curl -s -X POST localhost:8080/v1/bookings/bkg_000002/approve \
  -H 'Authorization: Bearer dev:lender1'
```

Interactive API docs: http://localhost:8080/docs

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## Deploy to Cloud Run

```bash
gcloud run deploy toolshare-api \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars TOOLSHARE_ENV=prod,TOOLSHARE_GCP_PROJECT=$PROJECT_ID \
  --set-secrets TOOLSHARE_STRIPE_SECRET_KEY=stripe-secret:latest
```

Prod requires: a Firestore database, a Stripe account with Connect (Express)
enabled, and Firebase Auth configured for Sign in with Apple + Google + phone.

## Architecture notes

- **State machine** (`app/state_machine.py`): every booking transition is
  role-checked, audited to a timeline, and idempotent. Routers orchestrate
  payment side effects around transitions; illegal jumps are impossible.
- **Money** (`app/services/payments.py`): borrower pays rental + 15% fee
  (min $1); deposit is a manual-capture PaymentIntent (auth hold), captured
  only on dispute; lender is paid the full rental via Stripe Connect Transfer
  on confirmed return.
- **Privacy**: listings expose only jittered coordinates; the exact address
  lives in a separate collection and appears only in the booking payload once
  the booking is CONFIRMED.
- **Repos** (`app/repos/`): protocol-based; in-memory for dev/tests, Firestore
  for prod, selected by `TOOLSHARE_ENV`.

## Not yet implemented (week-1 backlog)

- Cloud Tasks jobs: 24h request expiry, deposit auto-void, payout retry after
  late Connect onboarding
- FCM push notifications on booking events and messages
- Signed-URL photo upload to Cloud Storage
- Stripe webhook receiver (async payment confirmation for 3DS cards)
- Admin kill-switch endpoints
