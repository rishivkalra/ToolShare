# ToolShare Mobile (iOS + Android)

React Native app built with Expo — one TypeScript codebase shipping to both
the App Store and Google Play via EAS Build.

## Screens

- **Browse** — location-based search of tools nearby (list; map view next)
- **List a tool** — 60-second listing flow with price + deposit
- **Rentals** — all bookings with live state labels
- **Rental detail** — approve/decline, two-sided pickup confirmation, return,
  per-booking chat, reviews
- **Profile** — dev sign-in switcher, Stripe Connect payout onboarding

## Run against the local backend

```bash
cd backend && TOOLSHARE_ENV=dev .venv/bin/uvicorn app.main:app --port 8080   # terminal 1
cd mobile && npm install && EXPO_PUBLIC_API_URL=http://<your-lan-ip>:8080 npx expo start   # terminal 2
```

Scan the QR with the Expo Go app. Use the Profile tab to switch between dev
users (e.g. `lender1` / `borrower1`) and walk the whole rental loop between
two phones or two simulators.

## Production wiring (backlog)

- Firebase Auth: Sign in with Apple + Google + phone OTP -> `setAuthToken(idToken)`
- Stripe PaymentSheet for card/Apple Pay/Google Pay collection at first booking
- expo-notifications + FCM/APNs for booking events
- Photo upload (expo-image-picker -> signed Cloud Storage URLs)
- EAS Build + Submit: `eas build --platform all && eas submit`
