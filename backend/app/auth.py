"""Request authentication.

Prod: verifies Firebase ID tokens (Sign in with Apple / Google / phone OTP all
arrive as Firebase tokens from the mobile client).
Dev:  also accepts `Authorization: Bearer dev:<uid>` so the API is fully
      exercisable with curl and tests without any Firebase project.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings

_firebase_initialized = False


def _verify_firebase(token: str) -> str:
    global _firebase_initialized
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not _firebase_initialized:
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()
        _firebase_initialized = True
    decoded = fb_auth.verify_id_token(token)
    return decoded["uid"]


def current_uid(request: Request, settings: Settings = Depends(get_settings)) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = header.removeprefix("Bearer ").strip()

    if settings.dev_auth_active and token.startswith("dev:"):
        return token.removeprefix("dev:")

    try:
        return _verify_firebase(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
