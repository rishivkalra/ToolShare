# ToolShare Mobile (Flutter — iOS + Android)

One Dart codebase shipping to both the App Store and Google Play.

## Screens

- **Browse** — location-based search of tools nearby
- **Project** — the differentiator: describe a project ("build a raised garden
  bed"), Claude plans the tool list, and each tool is matched against listings
  actually available in your neighborhood — rent the whole kit
- **List** — 60-second listing flow with price + deposit
- **Rentals** — bookings with live state labels; detail screen has
  approve/decline, two-sided pickup confirmation, return, and per-booking chat
- **Profile** — dev sign-in switcher, Stripe Connect payout onboarding

## Setup

This repo contains the Dart source (`lib/`, `pubspec.yaml`). Generate the
platform folders once:

```bash
cd mobile
flutter create . --project-name toolshare --org com.toolshare --platforms ios,android
flutter pub get
```

## Run against the local backend

```bash
# terminal 1
cd backend && TOOLSHARE_ENV=dev .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080

# terminal 2 — point the app at your machine's LAN IP
cd mobile && flutter run --dart-define=API_URL=http://<your-lan-ip>:8080
```

Use the Profile tab to switch dev users (`lender1` / `borrower1`) and walk the
whole rental loop between two simulators.

Note for iOS/Android permission config (after `flutter create`): add
`NSLocationWhenInUseUsageDescription` to `ios/Runner/Info.plist` and
`ACCESS_FINE_LOCATION` to `android/app/src/main/AndroidManifest.xml`
(see geolocator's README for the exact snippets).

## Production wiring (backlog)

- `firebase_auth`: Sign in with Apple + Google + phone OTP →
  `ApiClient.instance.setToken(idToken)`
- `flutter_stripe`: PaymentSheet for Apple Pay / Google Pay at booking approval
- `firebase_messaging`: push for booking events + chat
- `image_picker` + signed Cloud Storage URLs for listing photos
- Store submission: `flutter build ipa` / `flutter build appbundle`
