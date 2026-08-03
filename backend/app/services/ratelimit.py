"""Sliding-window rate limiting.

Per-instance and in-memory: on Cloud Run with a handful of instances this
multiplies the effective limit by the instance count, which is fine — the
goal is stopping scripted abuse (Gemini quota burn, listing spam, digest
flooding), not precise metering. Swap for Redis when instance counts grow.

Keys are hashed so bearer tokens never sit in memory as-is.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int = 3600) -> bool:
        now = time.time()
        dq = self._hits[key]
        while dq and dq[0] <= now - window_seconds:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


def rate_limit(name: str, per_hour: int):
    """Route dependency: `dependencies=[rate_limit("plan", 20)]`.

    Identity = bearer token when present (per-user), else client IP
    (unauthenticated endpoints like search)."""

    def dep(request: Request):
        from ..deps import get_container  # late import: deps imports this module

        c = get_container()
        ident = request.headers.get("Authorization") or (
            request.client.host if request.client else "anon"
        )
        key = f"{name}:{hashlib.sha1(ident.encode()).hexdigest()[:16]}"
        if not c.ratelimit.allow(key, per_hour):
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please slow down and try again soon",
                headers={"Retry-After": "600"},
            )

    return Depends(dep)
