"""Dependency container: wires repos + payment provider per environment."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, get_settings
from .repos.base import BookingRepo, ListingRepo, MessageRepo, ReviewRepo, UserRepo
from .services.payments import FakePayments, PaymentProvider


@dataclass
class Container:
    users: UserRepo
    listings: ListingRepo
    bookings: BookingRepo
    messages: MessageRepo
    reviews: ReviewRepo
    payments: PaymentProvider


_container: Container | None = None


def build_container(settings: Settings) -> Container:
    if settings.env == "prod":
        from google.cloud import firestore

        from .repos.firestore import (
            FirestoreBookingRepo,
            FirestoreListingRepo,
            FirestoreMessageRepo,
            FirestoreReviewRepo,
            FirestoreUserRepo,
        )
        from .services.payments import StripePayments

        db = firestore.Client(
            project=settings.gcp_project or None, database=settings.firestore_database
        )
        return Container(
            users=FirestoreUserRepo(db),
            listings=FirestoreListingRepo(db),
            bookings=FirestoreBookingRepo(db),
            messages=FirestoreMessageRepo(db),
            reviews=FirestoreReviewRepo(db),
            payments=StripePayments(settings.stripe_secret_key, settings.service_base_url),
        )

    from .repos.memory import (
        MemoryBookingRepo,
        MemoryListingRepo,
        MemoryMessageRepo,
        MemoryReviewRepo,
        MemoryUserRepo,
    )

    return Container(
        users=MemoryUserRepo(),
        listings=MemoryListingRepo(),
        bookings=MemoryBookingRepo(),
        messages=MemoryMessageRepo(),
        reviews=MemoryReviewRepo(),
        payments=FakePayments(),
    )


def get_container() -> Container:
    global _container
    if _container is None:
        _container = build_container(get_settings())
    return _container


def reset_container() -> None:
    """Test hook."""
    global _container
    _container = None
