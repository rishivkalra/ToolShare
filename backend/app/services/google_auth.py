"""Google Sign-In: verifies Google Identity Services ID tokens.

The landing page renders the official "Sign in with Google" button, which
yields a signed ID token (JWT). We verify it server-side against Google's
tokeninfo endpoint and check the audience matches our OAuth client, then
mint a first-party session token (see app.auth).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass
class GoogleUser:
    sub: str  # Google's stable account id
    email: str
    name: str
    picture: str


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleUser: ...


class VerificationError(Exception):
    pass


class RealGoogleVerifier:
    def __init__(self, client_id: str):
        self.client_id = client_id

    def verify(self, credential: str) -> GoogleUser:
        try:
            resp = httpx.get(_TOKENINFO_URL, params={"id_token": credential}, timeout=10)
        except httpx.HTTPError as e:
            raise VerificationError(f"tokeninfo unreachable: {e}") from e
        if resp.status_code != 200:
            raise VerificationError("invalid Google credential")
        claims = resp.json()
        if claims.get("aud") != self.client_id:
            raise VerificationError("credential issued for a different app")
        if claims.get("iss") not in _GOOGLE_ISSUERS:
            raise VerificationError("unexpected issuer")
        sub = claims.get("sub", "")
        if not sub:
            raise VerificationError("credential missing subject")
        return GoogleUser(
            sub=sub,
            email=claims.get("email", ""),
            name=claims.get("name", "") or claims.get("email", "").split("@")[0],
            picture=claims.get("picture", ""),
        )


class FakeGoogleVerifier:
    """Dev/tests only: accepts `fake:<sub>:<email>:<name>` pseudo-credentials."""

    def verify(self, credential: str) -> GoogleUser:
        if not credential.startswith("fake:"):
            raise VerificationError("invalid Google credential")
        parts = credential.split(":", 3)
        if len(parts) < 2 or not parts[1]:
            raise VerificationError("invalid Google credential")
        sub = parts[1]
        email = parts[2] if len(parts) > 2 else f"{sub}@example.com"
        name = parts[3] if len(parts) > 3 else email.split("@")[0]
        return GoogleUser(sub=sub, email=email, name=name, picture="")


def build_verifier(env: str, google_client_id: str) -> Optional[GoogleVerifier]:
    """Real verifier whenever a client id is configured; fake in dev so the
    flow is testable end to end; None (feature off) in prod without a client."""
    if google_client_id:
        return RealGoogleVerifier(google_client_id)
    if env != "prod":
        return FakeGoogleVerifier()
    return None
