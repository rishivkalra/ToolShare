"""Web sign-in: Google Identity Services credential -> first-party session.

GET  /v1/auth/config   what the landing page should render (Google button
                       and/or the staging demo entry)
POST /v1/auth/google   verify a Google ID token, upsert the profile, return
                       a signed session token the SPA sends as its bearer
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import SESSION_TTL_SECONDS, mint_session
from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import UserProfile
from ..services.google_auth import VerificationError
from ..services.ratelimit import rate_limit

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class AuthConfig(BaseModel):
    google_client_id: str
    dev_auth: bool


@router.get("/config", response_model=AuthConfig)
def auth_config(settings: Settings = Depends(get_settings)):
    return AuthConfig(
        google_client_id=settings.google_client_id,
        dev_auth=settings.dev_auth_active,
    )


class GoogleSignIn(BaseModel):
    credential: str
    ref: str = ""  # inviter uid from a ?ref= link (give $10 / get $10)


class SessionResponse(BaseModel):
    token: str
    expires_in: int
    uid: str
    display_name: str
    email: str


@router.post("/google", response_model=SessionResponse,
             dependencies=[rate_limit("auth", 30)])
def google_sign_in(
    body: GoogleSignIn,
    settings: Settings = Depends(get_settings),
    c: Container = Depends(get_container),
):
    if c.google_auth is None:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured yet")
    try:
        guser = c.google_auth.verify(body.credential)
    except VerificationError:
        raise HTTPException(status_code=401, detail="Google sign-in failed — try again")

    uid = f"g{guser.sub}"
    existing = c.users.get(uid)
    user = existing or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    # Referral attribution: first sign-in only, never self-referral. The new
    # neighbor gets $10 now; the inviter is paid at the first confirmed rental.
    if existing is None and body.ref and body.ref != uid and c.users.get(body.ref):
        user.referred_by = body.ref
        user.credit_cents += 1000
        c.notifier.notify(
            uid, "Welcome — $10 rental credit applied 🎉",
            "Your neighbor's invite came with $10 off your first rental.",
            kind="system",
        )
    user.email = guser.email or user.email
    user.display_name = user.display_name or guser.name
    user.photo_url = user.photo_url or guser.picture
    c.users.upsert(user)

    return SessionResponse(
        token=mint_session(uid, settings.session_signing_key),
        expires_in=SESSION_TTL_SECONDS,
        uid=uid,
        display_name=user.display_name,
        email=user.email,
    )
