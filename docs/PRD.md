# ToolShare — Product Requirements Document

**Version:** 1.0 · **Date:** July 2026 · **Status:** Draft for 1-week MVP build
**Platform:** iOS (SwiftUI) · **Backend:** Python (FastAPI) on Google Cloud

---

## 1. Executive Summary

ToolShare is a hyperlocal peer-to-peer tool rental app. A neighbor who owns a circular saw lists it; a neighbor three streets over rents it for $5–$10 a day instead of buying a $120 tool they'll use twice. ToolShare handles discovery, booking, payment, and trust — the two neighbors handle a 90-second handoff at the front door.

**Why now / why us:** The category has been tried (SnapGoods, NeighborGoods died; Peerby, Yoodlize, Sparetoolz, ToolBevy survive at modest scale). The failures share known causes — supply/demand imbalance, high coordination friction relative to item value, and going too broad ("rent anything"). This PRD is deliberately narrow: **tools only, one neighborhood at a time, money changes hands from day one** (paying lenders solves the "why bother listing" problem; charging borrowers filters for real demand).

**North-star metric:** Completed rentals per active neighborhood per week.

---

## 2. Problem Statement

- The average power drill is used **~13 minutes in its entire lifetime**. Households collectively own thousands of dollars of idle tools.
- Buying a tool for a one-off job costs $40–$400; big-box rental (Home Depot) requires a truck trip, a deposit, and rigid hours.
- Neighbors are physically close to enormous idle inventory but have no low-friction, trusted way to transact.
- Existing "rent anything" marketplaces are too thin locally: you open the app and nothing is within walking distance, so you never open it again.

**The user's real alternative is not another app — it's Amazon Prime.** The product must beat "a new drill arrives tomorrow for $39" on speed, price, or conscience, ideally all three.

## 3. Goals & Non-Goals

### Goals (MVP, week 1)
1. A lender can list a tool with photo, price/day, and deposit in under 60 seconds.
2. A borrower can find tools within X miles, request dates, pay in-app, and coordinate pickup.
3. Money flows: platform collects payment, holds it, pays out to the lender after the rental completes, takes a service fee.
4. Basic trust: verified phone + payment method, mutual reviews, security deposit hold.
5. Launch to **one seed neighborhood** via TestFlight.

### Non-Goals (explicitly out of MVP)
- Android, web app, delivery/logistics, insurance product (beyond deposit), in-app disputes/arbitration UI, tool categories beyond tools (no party gear, no cameras), subscriptions, multi-language, damage-claim automation, background checks.

## 4. Market & Competitive Landscape

| Player | Model | Status (2026) | Lesson for us |
|---|---|---|---|
| **Peerby** (NL/EU/US) | Borrow free or rent from neighbors | Active, strongest in NL | Free borrowing kills lender motivation; hyperlocal density is everything |
| **Yoodlize** (US, Utah) | Rent anything P2P, $2k item coverage | Active, v3 app | Item-protection guarantee is a real conversion lever |
| **Fat Llama → Hygglo** | Rent anything, urban hubs | Acquired 2022, active in EU | Money-first P2P rental can reach 1.5M users; camera/AV gear dominated |
| **Sparetoolz** | Tools-only P2P | Active, small | Validates tools-only niche exists; poor density killed growth |
| **ToolBevy** | Tools + heavy equipment | Active, growing | Pro/restoration equipment is a lucrative adjacent segment |
| **SnapGoods** | Rent anything | **Dead** | "Everything except nobody gives a shit" — too broad, no density |
| **NeighborGoods** | Free sharing | **Dead** | More lenders than borrowers; no payments = no filter for real demand |
| **Home Depot Rental** | B2C counter rental | Active, incumbent | Price anchor: our $5–10/day vs. their $30–60/day + trip |

### Positioning
**"The tool library your street already owns."** Tools-only (differentiated from Peerby/Yoodlize's clutter), paid-only (differentiated from dead free-sharing models), density-first (one neighborhood seeded to 50+ listings before opening the next).

## 5. Target Users & Personas

1. **Homeowner Hank (lender), 35–65** — garage full of tools, likes helping neighbors, would list if it takes one minute and strangers don't waste his time. Motivated ~60% by community/conscience, ~40% by beer money.
2. **Renter Rachel (borrower), 25–40** — rents or owns a starter home, occasional projects (shelf, garden bed, bike repair). Doesn't want to own a hedge trimmer. Price-sensitive; trusts neighbors more than Craigslist strangers.
3. **DIY Dana (both sides)** — the power user who seeds a neighborhood. Owns 30 tools, borrows the 31st. Find 3–5 Danas per neighborhood before launch; they are the supply side.

## 6. Core User Journeys

### 6.1 Lender: list a tool (target: <60s)
Photo (camera or library) → title (autocomplete from tool taxonomy) → condition → price/day (smart default suggested from taxonomy, e.g. "Circular saws near you go for $8/day") → optional deposit (default suggested) → pickup zone (approximate map pin, exact address hidden until booking confirmed) → publish.

### 6.2 Borrower: rent a tool
Browse map/list within radius → tool detail (photos, price, deposit, lender rating, distance, availability calendar) → pick dates → pay (Apple Pay first, card fallback) → request sent → lender approves (or auto-accept if enabled) → in-app chat thread opens with pickup coordination → pickup: borrower taps "picked up", lender confirms → use → return: lender taps "returned, all good" → payout released, deposit hold voided → mutual reviews prompt.

### 6.3 Money flow (Stripe Connect)
- Borrower charged at booking approval: `days × rate + service fee`; deposit is an uncaptured authorization hold.
- Platform fee: **15% from borrower side** (lender receives full listed price — critical for supply-side motivation; lenders quote "$8/day," borrower sees "$9.20 + fees").
- Payout to lender via Stripe Connect Express transfer when the lender confirms return.
- Deposit: uncaptured `PaymentIntent`; captured (partially or fully) only if lender reports damage within 24h of return, else auto-voided.

### 6.4 Trust & safety
- Sign-in with Apple / phone OTP; a payment method on file is required to request a rental (identity anchor + demand filter).
- Approximate location on public listings; exact address revealed only after confirmed booking.
- Mutual 5-star reviews, shown on profiles; lenders can decline requests without penalty.
- Deposit hold covers loss/damage up to the hold amount; policy copy is explicit that ToolShare is a venue (v1) — a Yoodlize-style protection guarantee is a fast-follow, not MVP.

## 7. Functional Requirements (MVP)

| # | Requirement | Priority |
|---|---|---|
| F1 | Sign in with Apple + phone verification | P0 |
| F2 | Create/edit/pause listing: photos, title, description, condition, $/day, deposit, location | P0 |
| F3 | Geo search: list + map view, radius filter, category filter, text search | P0 |
| F4 | Availability calendar per listing; date-range selection | P0 |
| F5 | Booking request → lender approve/decline (24h expiry) | P0 |
| F6 | Payments: Apple Pay + card via Stripe; deposit auth hold; borrower-side 15% fee | P0 |
| F7 | Lender onboarding to Stripe Connect Express (hosted flow); payout on return confirmation | P0 |
| F8 | In-app chat per booking (text only) | P0 |
| F9 | Push notifications: request, approval, pickup/return reminders, messages | P0 |
| F10 | Pickup/return two-sided confirmation state machine | P0 |
| F11 | Mutual reviews after completion | P1 |
| F12 | Report listing/user; admin kill-switch for listings and users | P1 |
| F13 | Cancellation: free until approval; borrower cancel after approval refunds minus fee; lender cancel refunds all | P1 |
| F14 | Price suggestion from tool taxonomy | P2 |

### Booking state machine
`REQUESTED → APPROVED → (paid) CONFIRMED → PICKED_UP → RETURNED → COMPLETED`, with `DECLINED / EXPIRED / CANCELLED_BY_BORROWER / CANCELLED_BY_LENDER / DISPUTED` as terminal or side states. All transitions server-side, audited, idempotent.

## 8. Non-Functional Requirements

- **Latency:** search < 500ms p95; booking mutation < 1s p95.
- **Availability:** single-region acceptable for MVP (Cloud Run default SLA).
- **Privacy:** exact addresses encrypted at rest, never in listing payloads; chat retained 12 months; CCPA-basic delete-my-account flow (manual runbook is acceptable week 1).
- **Payments compliance:** no card data touches our servers — Stripe SDK tokenization only (SAQ-A).
- **Abuse:** rate limits on listing creation and messaging; image upload size caps; profanity/PII filter on chat is post-MVP.

## 9. System Architecture (Python + Google Cloud)

```
iOS (SwiftUI)
  ├── Firebase Auth (Sign in with Apple, phone OTP)
  ├── Stripe iOS SDK (Apple Pay, card entry, Connect onboarding via hosted web)
  └── HTTPS/JSON ──► Cloud Run: FastAPI (Python 3.12)
                        ├── Firestore (listings, bookings, users, chats)
                        ├── Cloud Storage + Cloud CDN (listing photos)
                        ├── Cloud Tasks (request expiry, payout jobs, reminders)
                        ├── Pub/Sub ► FCM (push notifications)
                        ├── Stripe API + webhook endpoint (payment lifecycle)
                        └── Cloud Logging / Error Reporting
Geo search: Firestore geohash queries (geofire) for MVP; swap to PostGIS
(Cloud SQL) only if/when query complexity demands it.
```

**Why these choices for a 1-week build:**
- **Cloud Run + FastAPI:** zero-ops containers, scale-to-zero (≈$0 idle), FastAPI gives typed request/response models and auto-generated OpenAPI docs that double as the iOS API contract.
- **Firestore over Cloud SQL:** no migrations, free tier, built-in listeners power chat with no websocket server. Trade-off accepted: weaker ad-hoc queries; geohash search is good enough at neighborhood scale.
- **Firebase Auth:** Sign in with Apple + phone OTP in hours, not days; ID tokens verified in FastAPI middleware.
- **Stripe Connect Express:** the only realistic way to do two-sided payouts + deposit holds in a week; hosted onboarding means no KYC UI to build.

### Data model (Firestore collections)
```
users/{uid}: display_name, photo, phone_verified, stripe_customer_id,
             stripe_connect_id, rating_avg, rating_count, created_at
listings/{id}: owner_uid, title, category, description, condition, photos[],
               price_per_day, deposit, geohash, approx_latlng, exact_address_ref,
               status(active|paused|removed), rating snapshot
bookings/{id}: listing_id, borrower_uid, lender_uid, date_range, state,
               price_breakdown, stripe_payment_intent, stripe_deposit_intent,
               timeline[] (audited transitions)
bookings/{id}/messages/{mid}: sender_uid, text, created_at
reviews/{id}: booking_id, from_uid, to_uid, stars, text
```

## 10. Monetization

- **15% borrower-side service fee** (industry range 10–25%; Fat Llama charged ~25% combined). Lender keeps 100% of list price.
- Rental floor $5 so fees don't round to zero.
- Later (not MVP): protection-plan upsell (~$1–2/rental), featured listings, pro-lender tier for high-inventory users, neighborhood expansion via HOA/community partnerships.
- Unit economics check: $8/day × 1.15 = $9.20 charged; $1.20 gross margin per rental-day minus ~$0.57 Stripe fees ⇒ thin at MVP scale. This is fine: week-one goal is proving transaction frequency, not margin. Pricing power comes later from protection plans, not the take rate.

## 11. Launch Plan (Week 1 = TestFlight, not App Store)

Apple review for a brand-new payments-enabled marketplace realistically takes 1–7 days and may bounce once. **Plan of record: TestFlight external beta to one seed neighborhood in week 1; App Store submission end of week 1, public listing week 2–3.**

- Pick one neighborhood (ideally the founder's). Recruit 3–5 "DIY Danas" in person; hand-seed 40–60 listings before inviting borrowers.
- Distribution: neighborhood Facebook group, Nextdoor post, flyers at the hardware store, QR codes on mailbox row.
- Success gate to open neighborhood #2: ≥10 completed paid rentals and ≥30% borrower repeat intent in week 2.

## 12. Success Metrics

| Metric | Week 2 target | Month 2 target |
|---|---|---|
| Listings in seed neighborhood | 50 | 150 |
| Completed paid rentals / week | 10 | 40 |
| Booking requests → completed | ≥60% | ≥75% |
| Median time-to-first-response (lender) | <4h | <1h |
| Damage/dispute rate | <5% | <2% |
| D30 borrower retention (≥2nd rental) | — | ≥25% |

## 13. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Empty-marketplace death (the category's #1 killer) | High | One neighborhood at a time; hand-seed supply; don't launch borrower marketing below 40 listings |
| Coordination friction > item value | High | Tools-only floor of $5; auto-accept option; pickup windows in chat quick-replies; "porch pickup" lockbox pattern encouraged in copy |
| Apple review rejection (marketplace/payments) | Medium | Physical-goods rental is correctly outside IAP (Guideline 3.1.1 exemption — like Airbnb/Uber); use Stripe, document the exemption in review notes; TestFlight decouples launch from review |
| Damage disputes sour early adopters | Medium | Deposit holds + photo-at-pickup prompt; founder personally mediates every dispute in month 1 |
| Liability (injury from a borrowed saw) | Medium | ToS: venue model, assumption of risk, arbitration clause; consult a lawyer before public App Store launch; exclude powder-actuated and gas-pressure tools from taxonomy v1 |
| Stripe Connect onboarding drop-off | Medium | Lenders can list before onboarding; Connect flow triggered only at first approved booking |

## 14. Open Questions

1. Deposit sizing: fixed suggestion per category vs. lender-set free-form? (MVP: lender-set with category default.)
2. Auto-accept default on or off? (MVP: off; measure response latency first.)
3. Is 15% the right fee for a $5 rental ($0.75)? Consider $1 minimum fee.
4. Insurance partner (e.g., embedded coverage à la Yoodlize's $2k guarantee) — required before scaling past friendly early adopters?

---

*Appendix A — 7-day build plan lives in `docs/LAUNCH_PLAN.md`.*
