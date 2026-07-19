"""Dependency container: wires repos + payment provider per environment."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, get_settings
from .repos.base import BookingRepo, ListingRepo, MessageRepo, ReviewRepo, UserRepo
from .services.payments import FakePayments, PaymentProvider
from .services.project_planner import ProjectPlanner, build_planner
from .services.tasks import FakeScheduler, TaskScheduler


@dataclass
class Container:
    users: UserRepo
    listings: ListingRepo
    bookings: BookingRepo
    messages: MessageRepo
    reviews: ReviewRepo
    payments: PaymentProvider
    planner: ProjectPlanner
    tasks: TaskScheduler


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
        from .services.tasks import CloudTasksScheduler

        db = firestore.Client(
            project=settings.gcp_project or None, database=settings.firestore_database
        )
        # Graceful staging fallbacks: real Stripe/Cloud Tasks only when
        # configured, so the service boots and is testable before launch keys
        # exist. FakePayments in prod means NO REAL CHARGES — staging only.
        if settings.stripe_secret_key:
            payments = StripePayments(settings.stripe_secret_key, settings.service_base_url)
        else:
            payments = FakePayments()
        if settings.tasks_queue and settings.service_base_url:
            tasks = CloudTasksScheduler(
                settings.gcp_project,
                settings.tasks_location,
                settings.tasks_queue,
                settings.service_base_url,
                settings.internal_task_secret,
            )
        else:
            tasks = FakeScheduler()
        return Container(
            users=FirestoreUserRepo(db),
            listings=FirestoreListingRepo(db),
            bookings=FirestoreBookingRepo(db),
            messages=FirestoreMessageRepo(db),
            reviews=FirestoreReviewRepo(db),
            payments=payments,
            planner=build_planner(settings.env, settings.anthropic_api_key,
                                  settings.planner, settings.gcp_project,
                                  settings.gemini_model),
            tasks=tasks,
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
        planner=build_planner(settings.env, settings.anthropic_api_key,
                                  settings.planner, settings.gcp_project,
                                  settings.gemini_model),
        tasks=FakeScheduler(),
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
