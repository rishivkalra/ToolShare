# ToolShare

Hyperlocal peer-to-peer tool rental: neighbors rent idle tools to each other for $5–$10/day instead of buying tools they'll use once.

- **Mobile app:** React Native (Expo, TypeScript) — one codebase for iOS + Android ([mobile/](mobile/))
- **Backend:** Python (FastAPI) on Google Cloud Run ([backend/](backend/))
- **Data:** Firestore + Cloud Storage
- **Payments:** Stripe Connect Express (Apple Pay / Google Pay, deposit holds, lender payouts)
- **Identity:** Firebase Auth (Sign in with Apple, Google, phone OTP)

## Repository layout

| Path | What's there |
|---|---|
| [backend/](backend/) | FastAPI service: listings + geo search, booking state machine, payments, chat, reviews. 21 passing tests; runs locally with zero credentials |
| [mobile/](mobile/) | Expo app: browse, list-a-tool, rental lifecycle, chat, payout onboarding |
| [docs/PRD.md](docs/PRD.md) | Market research, personas, functional spec, architecture, monetization, risks |
| [docs/LAUNCH_PLAN.md](docs/LAUNCH_PLAN.md) | Day-by-day plan to a TestFlight beta in one seed neighborhood |

## Quick start

```bash
cd backend
uv venv .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest tests/ -q          # run the test suite
TOOLSHARE_ENV=dev .venv/bin/uvicorn app.main:app --port 8080   # start the API
```

See [backend/README.md](backend/README.md) for a curl walkthrough of the full
rental money loop, and [mobile/README.md](mobile/README.md) to point the app
at it.
