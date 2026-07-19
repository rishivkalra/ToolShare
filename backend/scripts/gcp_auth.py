#!/usr/bin/env python
"""Browser OAuth for headless GCP deploys (no gcloud CLI needed).

Replicates `gcloud auth login --no-launch-browser`: prints an authorization
URL using the Google Cloud SDK's public installed-app OAuth client (the same
client identity every gcloud install ships with), the user approves in their
browser, Google displays an authorization code, and `exchange` trades it for
tokens.

Tokens are written to ~/.toolshare/gcp_token.json — OUTSIDE the repo. Never
commit them.

Usage:
  python scripts/gcp_auth.py url                 # print the URL to open
  python scripts/gcp_auth.py exchange <CODE>     # paste the code from browser
  python scripts/gcp_auth.py token               # print a fresh access token
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

# The Google Cloud SDK's public OAuth client (installed-app flow). This is not
# a secret in the confidential-client sense — it ships in every gcloud
# install; the user's consent in the browser is what grants access.
CLIENT_ID = "32555940559.apps.googleusercontent.com"
CLIENT_SECRET = "ZmssLNjJy2998hD4CTg2ejr2"
REDIRECT_URI = "https://sdk.cloud.google.com/authcode.html"
SCOPES = "https://www.googleapis.com/auth/cloud-platform"

STATE_DIR = Path.home() / ".toolshare"
VERIFIER_FILE = STATE_DIR / "pkce_verifier"
TOKEN_FILE = STATE_DIR / "gcp_token.json"


def make_url() -> str:
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    verifier = secrets.token_urlsafe(64)
    VERIFIER_FILE.write_text(verifier)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)


def exchange(code: str) -> None:
    verifier = VERIFIER_FILE.read_text().strip()
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code.strip(),
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print("Token exchange failed:", resp.status_code, resp.text)
        sys.exit(1)
    tokens = resp.json()
    tokens["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(tokens))
    os.chmod(TOKEN_FILE, 0o600)
    print("Authorized. Tokens saved to", TOKEN_FILE)


def access_token() -> str:
    tokens = json.loads(TOKEN_FILE.read_text())
    age = time.time() - tokens.get("obtained_at", 0)
    if age < tokens.get("expires_in", 3600) - 120:
        return tokens["access_token"]
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    fresh = resp.json()
    tokens.update(fresh)
    tokens["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(tokens))
    return tokens["access_token"]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "url"
    if cmd == "url":
        print(make_url())
    elif cmd == "exchange":
        exchange(sys.argv[2])
    elif cmd == "token":
        print(access_token())
    else:
        print(__doc__)
        sys.exit(1)
