"""Payment provider abstraction.

`StripePayments` is the production implementation (Stripe Connect Express):
  - rental charge: destination-less PaymentIntent on the platform account,
    confirmed off-session with the borrower's saved payment method
  - deposit: separate manual-capture PaymentIntent (auth hold, no capture
    unless the lender reports damage)
  - payout: Transfer to the lender's Connect account for the rental amount
    (platform keeps the borrower-side service fee)

`FakePayments` mirrors the interface for dev/tests with deterministic ids.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class PaymentResult:
    id: str
    status: str  # succeeded | requires_action | requires_capture | canceled | failed


@dataclass
class SetupIntentBundle:
    """Everything the mobile PaymentSheet needs to collect a card."""

    customer_id: str
    setup_intent_client_secret: str
    ephemeral_key_secret: str


class PaymentProvider(Protocol):
    def ensure_customer(self, uid: str, existing_customer_id: str) -> str: ...
    def create_setup_intent(self, customer_id: str) -> SetupIntentBundle: ...
    def card_last4(self, customer_id: str) -> Optional[str]:
        """Last4 of the customer's saved card, or None if no card on file."""
        ...
    def charge_rental(
        self, customer_id: str, amount_cents: int, booking_id: str
    ) -> PaymentResult: ...
    def hold_deposit(
        self, customer_id: str, amount_cents: int, booking_id: str
    ) -> PaymentResult: ...
    def void_deposit(self, deposit_intent_id: str) -> None: ...
    def capture_deposit(self, deposit_intent_id: str, amount_cents: Optional[int]) -> None: ...
    def refund_rental(self, payment_intent_id: str, amount_cents: Optional[int]) -> None: ...
    def payout_lender(
        self, connect_account_id: str, amount_cents: int, booking_id: str
    ) -> str: ...
    def onboarding_link(self, uid: str, existing_connect_id: str) -> tuple[str, str]:
        """Returns (connect_account_id, onboarding_url)."""
        ...


class FakePayments:
    """Dev/test provider. Records every call for assertions."""

    def __init__(self):
        self._n = itertools.count(1)
        self.charges: list[tuple[str, int]] = []
        self.deposits: list[tuple[str, int]] = []
        self.voided: list[str] = []
        self.captured: list[tuple[str, Optional[int]]] = []
        self.refunds: list[tuple[str, Optional[int]]] = []
        self.payouts: list[tuple[str, int]] = []
        self.fail_next_charge = False

    def ensure_customer(self, uid: str, existing_customer_id: str) -> str:
        return existing_customer_id or f"cus_fake_{uid}"

    def create_setup_intent(self, customer_id: str) -> SetupIntentBundle:
        n = next(self._n)
        return SetupIntentBundle(
            customer_id=customer_id,
            setup_intent_client_secret=f"seti_fake_{n}_secret",
            ephemeral_key_secret=f"ek_fake_{n}",
        )

    def card_last4(self, customer_id: str) -> Optional[str]:
        return "4242"  # staging: every customer "has" a saved test card

    def charge_rental(self, customer_id, amount_cents, booking_id) -> PaymentResult:
        if self.fail_next_charge:
            self.fail_next_charge = False
            return PaymentResult(id=f"pi_fail_{next(self._n)}", status="failed")
        pid = f"pi_fake_{next(self._n)}"
        self.charges.append((pid, amount_cents))
        return PaymentResult(id=pid, status="succeeded")

    def hold_deposit(self, customer_id, amount_cents, booking_id) -> PaymentResult:
        pid = f"pi_dep_fake_{next(self._n)}"
        self.deposits.append((pid, amount_cents))
        return PaymentResult(id=pid, status="requires_capture")

    def void_deposit(self, deposit_intent_id: str) -> None:
        self.voided.append(deposit_intent_id)

    def capture_deposit(self, deposit_intent_id, amount_cents=None) -> None:
        self.captured.append((deposit_intent_id, amount_cents))

    def refund_rental(self, payment_intent_id, amount_cents=None) -> None:
        self.refunds.append((payment_intent_id, amount_cents))

    def payout_lender(self, connect_account_id, amount_cents, booking_id) -> str:
        tid = f"tr_fake_{next(self._n)}"
        self.payouts.append((tid, amount_cents))
        return tid

    def onboarding_link(self, uid, existing_connect_id) -> tuple[str, str]:
        acct = existing_connect_id or f"acct_fake_{uid}"
        return acct, f"https://connect.stripe.example/onboard/{acct}"


class StripePayments:
    def __init__(self, secret_key: str, service_base_url: str):
        import stripe

        self.stripe = stripe
        self.stripe.api_key = secret_key
        self.base_url = service_base_url

    def ensure_customer(self, uid: str, existing_customer_id: str) -> str:
        if existing_customer_id:
            return existing_customer_id
        customer = self.stripe.Customer.create(metadata={"uid": uid})
        return customer.id

    def create_setup_intent(self, customer_id: str) -> SetupIntentBundle:
        setup = self.stripe.SetupIntent.create(customer=customer_id, usage="off_session")
        # Ephemeral key lets the mobile PaymentSheet act as this customer.
        key = self.stripe.EphemeralKey.create(
            customer=customer_id, stripe_version="2024-06-20"
        )
        return SetupIntentBundle(
            customer_id=customer_id,
            setup_intent_client_secret=setup.client_secret,
            ephemeral_key_secret=key.secret,
        )

    def _default_pm(self, customer_id: str) -> Optional[str]:
        pms = self.stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
        return pms.data[0].id if pms.data else None

    def card_last4(self, customer_id: str) -> Optional[str]:
        pms = self.stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
        return pms.data[0].card.last4 if pms.data else None

    def charge_rental(self, customer_id, amount_cents, booking_id) -> PaymentResult:
        pm = self._default_pm(customer_id)
        intent = self.stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            customer=customer_id,
            payment_method=pm,
            off_session=True,
            confirm=True,
            metadata={"booking_id": booking_id, "kind": "rental"},
        )
        return PaymentResult(id=intent.id, status=intent.status)

    def hold_deposit(self, customer_id, amount_cents, booking_id) -> PaymentResult:
        pm = self._default_pm(customer_id)
        intent = self.stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            customer=customer_id,
            payment_method=pm,
            off_session=True,
            confirm=True,
            capture_method="manual",
            metadata={"booking_id": booking_id, "kind": "deposit"},
        )
        return PaymentResult(id=intent.id, status=intent.status)

    def void_deposit(self, deposit_intent_id: str) -> None:
        self.stripe.PaymentIntent.cancel(deposit_intent_id)

    def capture_deposit(self, deposit_intent_id, amount_cents=None) -> None:
        kwargs = {"amount_to_capture": amount_cents} if amount_cents else {}
        self.stripe.PaymentIntent.capture(deposit_intent_id, **kwargs)

    def refund_rental(self, payment_intent_id, amount_cents=None) -> None:
        kwargs = {"amount": amount_cents} if amount_cents else {}
        self.stripe.Refund.create(payment_intent=payment_intent_id, **kwargs)

    def payout_lender(self, connect_account_id, amount_cents, booking_id) -> str:
        transfer = self.stripe.Transfer.create(
            amount=amount_cents,
            currency="usd",
            destination=connect_account_id,
            metadata={"booking_id": booking_id},
        )
        return transfer.id

    def onboarding_link(self, uid, existing_connect_id) -> tuple[str, str]:
        acct_id = existing_connect_id
        if not acct_id:
            acct = self.stripe.Account.create(
                type="express",
                capabilities={"transfers": {"requested": True}},
                metadata={"uid": uid},
            )
            acct_id = acct.id
        link = self.stripe.AccountLink.create(
            account=acct_id,
            refresh_url=f"{self.base_url}/connect/refresh",
            return_url=f"{self.base_url}/connect/done",
            type="account_onboarding",
        )
        return acct_id, link.url
