"""Government-ID verification (the top rung of the trust ladder).

Prod: Stripe Identity hosted verification — we create a VerificationSession
and send the user to Stripe's flow; the `identity.verification_session.verified`
webhook flips `id_verified` on the profile.
Dev/staging: FakeIdentity verifies instantly so the whole ladder is testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class IdentitySession:
    url: str  # hosted verification URL ("" when verified instantly)
    verified_now: bool


class IdentityProvider(Protocol):
    def start(self, uid: str) -> IdentitySession: ...


class FakeIdentity:
    def start(self, uid: str) -> IdentitySession:
        return IdentitySession(url="", verified_now=True)


class StripeIdentity:
    def __init__(self, secret_key: str, return_url: str):
        import stripe

        self.stripe = stripe
        self.secret_key = secret_key
        self.return_url = return_url

    def start(self, uid: str) -> IdentitySession:
        session = self.stripe.identity.VerificationSession.create(
            api_key=self.secret_key,
            type="document",
            metadata={"uid": uid},
            options={"document": {"require_matching_selfie": True}},
            return_url=f"{self.return_url}/app/#/profile" if self.return_url else None,
        )
        return IdentitySession(url=session.url, verified_now=False)
