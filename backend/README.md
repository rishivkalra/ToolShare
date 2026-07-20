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
  -d '{"listing_id":"<id from the listing response>","start_date":"2026-08-01","end_date":"2026-08-02"}'

# lender approves (charges borrower, holds deposit)
curl -s -X POST localhost:8080/v1/bookings/<booking id>/approve \
  -H 'Authorization: Bearer dev:lender1'
```

Interactive API docs: http://localhost:8080/docs

## Tests

```bash
.venv/bin/python -m pytest tests/ -q          # 31 unit/API tests
.venv/bin/python scripts/e2e_demo.py          # full acceptance run over real HTTP
```

`e2e_demo.py` boots the server itself and drives all 15 product flows end to
end (listing, search, AI kit, kit checkout, payment setup, approve/charge,
privacy, chat, handoff, return, payout sweep, reviews, expiry job). Run it
before any deploy — exit code 0 means the stack is release-ready.

## Deploy to Cloud Run

```bash
PROJECT_ID=your-project ./deploy.sh
```

`deploy.sh` header lists the one-time setup (enable APIs, Firestore database,
Cloud Tasks queue, secrets). Prod requires: a Stripe account with Connect
(Express) enabled, an Anthropic API key for project kits, and Firebase Auth
configured for Sign in with Apple + Google + phone.

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

## Lifecycle jobs & payments plumbing

- **Request expiry**: every booking request schedules a Cloud Tasks callback
  to `/internal/tasks/expire-booking` after 24h; unanswered requests expire.
  Handlers are idempotent and protected by `TOOLSHARE_INTERNAL_TASK_SECRET`.
- **PaymentSheet setup**: `POST /v1/users/me/setup-intent` returns the
  customer id + SetupIntent client secret + ephemeral key the mobile Stripe
  PaymentSheet needs to save a card (charged off-session at approval).
- **Payout sweep**: rentals returned before the lender finished Connect
  onboarding complete with a pending payout; `POST /v1/users/me/connect/complete`
  (called when the app returns from hosted onboarding) sweeps and pays them.
- **Kit checkout**: `POST /v1/projects/checkout` turns a project kit into one
  booking request per listing, best-effort per item.

## Not yet implemented (backlog)

- FCM push notifications on booking events and messages
- Signed-URL photo upload to Cloud Storage
- Stripe webhook receiver (async payment confirmation for 3DS cards)
- Deposit auto-void delay window (currently voided synchronously at return)
- Admin kill-switch endpoints
