# ToolShare

Hyperlocal peer-to-peer tool rental: neighbors rent idle tools to each other for $5–$10/day instead of buying tools they'll use once.

- **iOS app:** SwiftUI
- **Backend:** Python (FastAPI) on Google Cloud Run
- **Data:** Firestore + Cloud Storage
- **Payments:** Stripe Connect Express (Apple Pay, deposit holds, lender payouts)
- **Identity:** Firebase Auth (Sign in with Apple, phone OTP)

## Docs

- [Product Requirements Document](docs/PRD.md) — market research, personas, functional spec, architecture, monetization, risks
- [7-Day Build & Launch Plan](docs/LAUNCH_PLAN.md) — day-by-day plan to a TestFlight beta in one seed neighborhood
