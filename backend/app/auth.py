"""Request authentication.

Three accepted bearer token forms:
  st1.<payload>.<sig>  first-party session token minted after Google Sign-In
                       (HMAC-signed, stateless — works across Cloud Run
                       instances with no session store)
  dev:<uid>            dev/staging only, for curl and tests
  <firebase jwt>       mobile clients (Sign in with Apple / Google / phone)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings

SESSION_TTL_SECONDS = 30 * 86400

_firebase_initialized = False


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64e(mac)


def mint_session(uid: str, secret: str, ttl: int = SESSION_TTL_SECONDS) -> str:
    payload = _b64e(json.dumps({"u": uid, "e": int(time.time()) + ttl}).encode())
    return f"st1.{payload}.{_sign(payload, secret)}"


def verify_session(token: str, secret: str) -> str:
    """Returns the uid or raises ValueError."""
    try:
        _, payload_b64, sig = token.split(".", 2)
        if not hmac.compare_digest(sig, _sign(payload_b64, secret)):
            raise ValueError("bad signature")
        payload = json.loads(_b64d(payload_b64))
        if payload["e"] < time.time():
            raise ValueError("expired")
        return payload["u"]
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError("malformed token") from e


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

    if token.startswith("st1."):
        try:
            return verify_session(token, settings.session_signing_key)
        except ValueError:
            raise HTTPException(status_code=401, detail="Session expired — sign in again")

    try:
        return _verify_firebase(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
