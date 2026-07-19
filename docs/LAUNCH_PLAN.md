# ToolShare — 7-Day Build & Launch Plan (iOS + Python/GCP)

**Goal:** live TestFlight beta in one seed neighborhood by Day 7, App Store submission on Day 7.
**Team assumption:** 1–2 builders using AI-assisted development, full-time.

## Ground rules that make one week possible

1. **Buy, don't build:** Firebase Auth (identity), Stripe Connect Express (payments/KYC/payouts), Firestore listeners (chat), FCM (push). The only truly custom code is the booking state machine and the listing/search UX.
2. **TestFlight is the launch.** App Store review for a new payments marketplace takes days and may bounce; external TestFlight review is typically ~24h. Public App Store is week 2–3.
3. **One neighborhood.** Supply density beats features. Day 6–7 is spent recruiting lenders in person, not polishing animations.
4. **Cut anything that isn't the money loop.** The demo that matters: list a saw → neighbor books and pays → handoff → return → lender gets paid.

## Day-by-day

### Day 0 (today): accounts & skeletons
- Apple Developer account (if new, enroll NOW — approval can take 24–48h and blocks everything).
- GCP project, enable Cloud Run/Firestore/Storage/Tasks/Pub-Sub; Firebase project linked; Stripe account, enable Connect (Express).
- Repo scaffolding: FastAPI app with health check deployed to Cloud Run via `gcloud run deploy`; SwiftUI app shell with Firebase SDK compiling on device.

### Day 1: identity + listings API
- Firebase Auth: Sign in with Apple + phone OTP; FastAPI middleware verifying ID tokens.
- Listings CRUD: Firestore models, photo upload to Cloud Storage via signed URLs, geohash on write.
- iOS: auth flow, "create listing" screen (photo, title, price, deposit, map pin).

### Day 2: search + browse
- Geo query endpoint (geohash bounding boxes + client-side distance sort), category/text filter.
- iOS: browse list + MapKit map view, listing detail screen with availability calendar.

### Day 3: bookings + payments (the hard day)
- Booking state machine in FastAPI with idempotent transitions + Cloud Tasks for 24h request expiry.
- Stripe: customer creation, PaymentIntent (rental + fee) confirmed with Apple Pay via Stripe iOS SDK; separate uncaptured PaymentIntent for the deposit; webhook endpoint on Cloud Run.
- iOS: request-to-book flow with Apple Pay sheet.

### Day 4: payouts + chat + push
- Stripe Connect Express hosted onboarding (triggered at first approved booking); transfer to lender on return confirmation; deposit auto-void via Cloud Tasks 24h after return.
- Chat: Firestore subcollection + snapshot listeners on iOS.
- FCM push: booking events + new messages.

### Day 5: the handoff loop + reviews + hardening
- Pickup/return two-sided confirmation UI; photo-at-pickup prompt.
- Mutual reviews; report/block; admin kill-switch (can be a protected FastAPI endpoint + you with curl).
- ToS + privacy policy pages (template + lawyer pass later), account-deletion path (App Store requirement), rate limits.

### Day 6: polish + TestFlight
- App icon, empty states, onboarding copy, crash pass on physical device.
- Archive → App Store Connect → external TestFlight review submission.
- Print flyers/QR codes; message the neighborhood Facebook group and 3–5 pre-recruited lender "anchors."

### Day 7: seed the neighborhood + submit for App Store review
- In-person lender onboarding blitz: target 40+ listings before inviting borrowers.
- Founder does a real end-to-end rental with a real neighbor and real money.
- Submit App Store review with notes: physical-service marketplace, payments via Stripe (Guideline 3.1.1 exemption, same category as Airbnb/TaskRabbit), demo account + demo video included.

## Biggest schedule risks
1. **Apple Developer enrollment delay** — start Day 0, hour 0.
2. **Stripe Connect platform review** — Stripe may ask questions about your platform before enabling live Connect charges; run the whole week in test mode and file for live access on Day 1.
3. **App Store review bounce** — mitigated by TestFlight-first; common marketplace rejection reasons: missing account deletion, unclear payment disclosure, thin ToS.
4. **Day-3 payments overrun** — if deposits threaten the schedule, ship v0 without deposit holds (lender-accepts-risk toggle) and add holds in week 2.
