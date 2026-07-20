# ToolShare — Competitive Gap Analysis & Viral Growth Plan

**Date:** July 2026 · **Inputs:** live competitor research (July 2026), PRD.md, MOAT.md, shipped product audit
**Question answered:** what must we build — and in what order — to be clearly better than every competitor and structurally viral?

---

## 1. Competitor intelligence (fresh, July 2026)

| Player | Model & fee | Trust stack | Notable 2025–26 developments | The lesson |
|---|---|---|---|---|
| **Peerby** (NL/EU) | Borrower **subscription** + fees | Guarantee to item value | **Pulled from Google Play Jan 2025**; Trustpilot full of "trapped into a paid subscription — you pay before you know the item is available" | Paywalling *contact* kills the funnel. Monetize the transaction, never the conversation |
| **Yoodlize** (US) | Rent anything, per-rental fee | **Stripe Identity ID verification**, **$2,000 item guarantee** (claim within 24h + proof of purchase), owner earnings dashboard | v3 app: in-app cancellations with upfront refund math | Protection guarantee + ID verify are the conversion levers; owner dashboard drives supply retention |
| **Hygglo** (Nordics, absorbed Fat Llama) | Rent anything, **20% commission** | **BankID identity + automated credit check on borrowers**, Omocom insurance ≈ **$3,000/item, no excess**, rental confirmed only after payment *and* verification | Hygglo Care branded protection for lenders | The strongest trust stack in the category — and they still charge 20% (we charge 15% and pay lenders 100% of list) |
| **ToolBevy** (US, 2024) | Tools + heavy/restoration equipment; free up to 10 listings, 1 photo each | Thin | Growing city-by-city (SEO pages per metro) | Fast follower in *our* niche; competes on breadth (heavy equipment), not experience. Their 1-photo limit is a UX gap we already beat |
| **Sparetoolz** (US) | Tools-only | Thin | Hourly/daily/weekly/monthly rates | Validates duration-tiered pricing; never solved density |
| **BuyNothing** (US, free) | Gift economy, no money | Community norms | Community-builder program + "sprouting" groups; a Berkeley lending library hit 60 shared items in weeks | The virality blueprint: local champions + visible community identity — bolt this onto a paid marketplace |
| **Home Depot / Sunbelt** | Counter rental $30–60/day | Corporate | — | Our price anchor and our copy foil ("skip the truck trip") |
| **Amazon Prime** | Buy, arrives tomorrow | — | — | The real competitor. We must win on price, conscience, *and* not-losing-a-garage-to-clutter |

**Category obituaries** (why the graveyard exists): SnapGoods/NeighborGoods died from empty-map cold start and free-sharing (no demand filter). Peerby's stumble adds a third cause: **monetization placed upstream of value**.

## 2. Where ToolShare stands today

**Shipped and working (verified in prod):** money loop with 15% borrower fee + deposit holds (Stripe abstraction, staging fake), 11-state audited booking machine, geo search, photo listings (≤8 photos, camera capture + client downscale), per-booking chat, mutual reviews, **AI project kits with one-tap kit checkout (Gemini)** — no competitor has this, rental-day counters + per-tool earnings dashboard, card-on-file gate before booking, address privacy until confirmation, reports, Google OAuth + landing page, CI + one-command GCP deploy.

**Honest self-assessment vs the field:** our *transaction core* and *AI layer* beat everyone. Our *trust ceiling* (no ID verify, no guarantee, venue-only deposit) is below Yoodlize/Hygglo, and our *discovery surface* (no map, no calendar UI, no filters, no notifications) is below all of them. Nobody wins on landing-page beauty; markets are won on liquidity, trust, and repeat rate.

## 3. Gap matrix — us vs. the four that matter

✅ have · 🟡 partial (API exists, no UX / staging only) · ❌ missing

| Capability | Us | Yoodlize | Hygglo | ToolBevy | Priority for us |
|---|---|---|---|---|---|
| Deposit hold (uncaptured auth) | ✅ | 🟡 | ✅ | ❌ | — |
| Lender keeps 100% of price | ✅ | ❌ | ❌ | ✅ | — (market in copy) |
| AI project kits / intent search | ✅ | ❌ | ❌ | ❌ | — (double down) |
| Owner earnings dashboard | ✅ | ✅ | 🟡 | ❌ | — |
| Real charges (live Stripe) | 🟡 fake | ✅ | ✅ | ✅ | **P0** |
| Availability calendar UI | 🟡 API blocks overlap | ✅ | ✅ | 🟡 | **P0** |
| Map view of nearby tools | ❌ | ✅ | ✅ | ✅ | **P0** |
| Push/email notifications | ❌ | ✅ | ✅ | ✅ | **P0** — response latency is the #1 funnel killer |
| ID verification | ❌ | ✅ Stripe Identity | ✅ BankID+credit | ❌ | **P0** (same Stripe stack we already use) |
| Protection guarantee ($) | ❌ venue-only | ✅ $2k | ✅ ~$3k | ❌ | **P0** (self-underwritten cap at launch) |
| Cancellation w/ upfront refund math | 🟡 states exist | ✅ | ✅ | ❌ | **P1** |
| Instant book for trusted renters | ❌ | 🟡 | ✅ | ❌ | **P1** |
| Duration-tiered pricing (wk/mo) | ❌ | ✅ | ✅ | ✅ | **P1** |
| Favorites / saved search + alerts | ❌ | ✅ | ✅ | ❌ | **P1** |
| Handoff condition photos | ❌ | 🟡 | ✅ | ❌ | **P1** |
| Native iOS/Android in stores | 🟡 Flutter scaffold | ✅ | ✅ | ✅ | **P1–P2** |
| Delivery option | ❌ | ❌ | 🟡 | ❌ | ❌ skip (Peerby Go's cost sink) |

## 4. The world-class UX brainstorm — beyond parity

Parity doesn't make an app viral. These are the experiences no competitor has, ranked by (impact × feasibility on our stack):

### 4.1 Supply side: "list a tool in 15 seconds" — **photo-to-listing AI**
Snap one photo → Gemini vision identifies the tool ("DeWalt DCD771 20V drill"), writes title/description/category, and suggests price + deposit from category norms. Owner taps *confirm*. Listing friction is THE supply constraint in this category (ToolBevy caps at 1 photo; most owners abandon at the form). We already have the Vertex AI plumbing — this is one endpoint + one screen. **This is the demo moment that makes people show the app to a neighbor.**

### 4.2 The viral unit: **shareable project-kit pages**
A kit result ("Raised garden bed — 6 tools, $54/weekend vs $610 to buy, all within 4 blocks") becomes a public URL with a beautiful OG card. People don't share marketplaces; they share *projects*. Every kit share seeds both demand (renters) and supply ("I own 2 of these 6 — I could earn $26"). Add "built with ToolShare" photo moments after completion.

### 4.3 Neighborhood identity & FOMO: **street-level counters and gates**
- Public per-neighborhood pages: "**Maple St: 212 tools, $14,300 in purchases avoided, 4.2 tons of stuff not manufactured**." (BuyNothing proves identity + counters drive local virality; we add money.)
- **Locked-neighborhood waitlist**: below seed density the app shows "23 tools listed here — unlocks at 40. Invite 3 neighbors to jump the line." Scarcity + a concrete invite action = built-in viral gate that also *protects us from empty-map death*.
- Founding-lender badge + 0% fees for life for the first 5 lenders per neighborhood (the DIY-Dana program from MOAT.md, productized).

### 4.4 Demand→supply flywheel: **"wanted nearby" signals**
Every unmatched search and kit gap is already logged server-side. Surface it: weekly digest to owners — "3 neighbors needed a tile saw this month; tile saws near you earn ~$12/day." One-tap "I have one" → prefilled listing (via 4.1). No competitor closes this loop; it converts demand data into inventory automatically.

### 4.5 Trust theater that's real: **verification ladder + guarantee**
Visible profile ladder — 📱 phone → 💳 card → 🪪 ID (Stripe Identity) → ⭐ 5 rentals. Instant book unlocks at ID+card. **ToolShare Guarantee**: up to $2,500 against damage/theft, funded by a $1.50/rental protection line item (Hygglo shows renters accept this; it's margin *and* trust). Handoff photos (borrower + lender snap at pickup/return; Gemini flags visible damage diffs) make claims adjudicable in minutes.

### 4.6 Retention: **project guides + seasonal rhythm**
After a kit rental, Gemini generates the step-by-step build guide referencing the exact rented tools (incl. safety notes) — the app stays open *during* the project, and finished-project photos feed 4.2. Seasonal pushes with local inventory ("Leaf-season: 4 blowers within 6 blocks, from $6/day"). Re-book in one tap ("rent the drill again").

### 4.7 Micro-delights (cheap, compounding)
Earnings confetti + "your drill paid for itself" milestones · garage-value estimator during onboarding ("your garage could earn ~$1,400/yr") · borrower savings ledger ("you've saved $312 vs buying") · porch-pickup mode with lockbox-code field in chat quick-replies · Apple/Google Wallet pass for pickup with map + code.

## 5. The build plan

Three sprints, each shippable and verified like everything so far (unit + e2e + Playwright + prod smoke). Effort: S ≤ 1 day · M 1–3 days · L 3–5 days.

### Sprint 1 — "Trust & table stakes" (close the P0 gaps)
| # | Feature | Effort | Notes |
|---|---|---|---|
| 1.1 | **Availability calendar**: `GET /v1/listings/{id}/availability`, blocked-date picker in detail modal, owner block-out dates | M | Overlap logic exists; expose + visualize |
| 1.2 | **Map view**: toggle on browse, pins from jittered coords (Leaflet + OSM tiles, no key needed) | M | Biggest perceived-liquidity win |
| 1.3 | **Notifications**: email (SendGrid/Gmail API) + web push on request/approve/message/pickup/return-due; FCM later for Flutter | L | Attacks lender response latency, the #1 funnel metric |
| 1.4 | **ID verification**: Stripe Identity session endpoint + profile badge + verification ladder UI | M | Same Stripe account we already integrate |
| 1.5 | **ToolShare Guarantee v1**: $1.50/rental protection line, $2,500 cap, claims flow = report + captured deposit + manual review; policy page | M | Self-underwritten at neighborhood scale; insurance partner later |
| 1.6 | **Live Stripe keys + webhook receiver** (3DS async confirmation) | M | Flips staging→real money; webhook completes the checklist |
| 1.7 | Cancellation UX with upfront refund math (policy from PRD F13) | S | States already exist |

### Sprint 2 — "The viral engine"
| # | Feature | Effort | Notes |
|---|---|---|---|
| 2.1 | **Photo-to-listing AI** (Gemini vision → prefilled listing) | M | Reuses planner auth + photo pipeline |
| 2.2 | **Shareable kit pages** `/kit/{id}` with OG image + "I own one of these" CTA | M | The viral unit |
| 2.3 | **Neighborhood pages + counters** (tools, $ saved, leaderboard) `/n/{geohash-name}` | M | Public = SEO surface too |
| 2.4 | **Waitlist/unlock gate** + invite links with attribution (`?ref=uid`) | M | Viral coefficient becomes measurable |
| 2.5 | **Referral credits**: give $10 / get $10 rental credit ledger | M | Standard, works |
| 2.6 | **Wanted-nearby digest**: weekly job aggregating unmatched searches + kit gaps per geohash → email to owners | M | Flywheel from MOAT.md, first automated |
| 2.7 | Instant book toggle (auto-approve for ID-verified borrowers) | S | |

### Sprint 3 — "Retention & depth"
| # | Feature | Effort | Notes |
|---|---|---|---|
| 3.1 | Project guides post-kit-rental (Gemini, references rented tools, safety notes) | M | |
| 3.2 | Handoff condition photos + AI damage diff on return | M | Completes the guarantee story |
| 3.3 | Weekly/monthly pricing tiers + smart price suggestions from local data | S | |
| 3.4 | Favorites, saved searches with alert emails | S | |
| 3.5 | Savings/earnings ledgers, milestones, garage-value estimator | S | |
| 3.6 | Flutter app: restyle to v2 design, point at prod, TestFlight submission | L | Store presence gates nothing above — web-first is working |

### Explicitly not doing (and why)
- **Delivery/logistics** — Peerby Go's cost sink; contradicts the walkable-density thesis.
- **Subscriptions** — Peerby's fatal lesson; anything that paywalls *contact* is banned.
- **"Rent anything" breadth** — SnapGoods' grave; tools-only keeps the taxonomy, pricing AI, and kits sharp.
- **Heavy equipment (ToolBevy's lane)** — insurance/liability profile is a different business; revisit post-density.

## 6. What "viral" means, measurably

| Metric | Definition | Target after Sprint 2 |
|---|---|---|
| K-factor | invites sent × conversion, via `?ref=` attribution | > 0.4 (local apps rarely exceed 1; gates + kit shares are the levers) |
| Kit-share rate | kits shared / kits generated | > 15% |
| Time-to-first-response | lender response to request (push attacks this) | < 1h median |
| Listing conversion | photo-to-listing starts → published | > 70% |
| Neighborhood unlock rate | waitlisted hoods reaching 40 listings / month | the expansion engine |
| D30 repeat borrower | ≥ 2nd rental | ≥ 25% (PRD target, now instrumentable) |

## 7. Recommended immediate next step

Sprint 1 in order 1.2 → 1.1 → 1.3 → 1.4/1.5 → 1.6: the map and calendar change perceived liquidity this week; notifications change funnel completion; ID + guarantee change conversion; live keys change it from staging to a business. Sprint 2 then makes growth structural rather than hoped-for.
