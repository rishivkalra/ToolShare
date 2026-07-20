"""Dependency container: wires repos + payment provider per environment."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, get_settings
from .repos.base import (
    BookingRepo,
    KitRepo,
    ListingRepo,
    MessageRepo,
    NotificationRepo,
    PushSubRepo,
    ReportRepo,
    ReviewRepo,
    UserRepo,
    WantedRepo,
)
from .services.google_auth import GoogleVerifier, build_verifier
from .services.identity import FakeIdentity, IdentityProvider, StripeIdentity
from .services.notify import Notifier
from .services.tool_id import ToolIdentifier, build_identifier
from .services.payments import FakePayments, PaymentProvider
from .services.photos import GcsPhotoStore, MemoryPhotoStore, PhotoStore
from .services.project_planner import ProjectPlanner, build_planner
from .services.tasks import FakeScheduler, TaskScheduler


@dataclass
class Container:
    users: UserRepo
    listings: ListingRepo
    bookings: BookingRepo
    messages: MessageRepo
    reviews: ReviewRepo
    reports: ReportRepo
    payments: PaymentProvider
    planner: ProjectPlanner
    tasks: TaskScheduler
    photos: PhotoStore
    google_auth: GoogleVerifier | None
    notifications: NotificationRepo
    push_subs: PushSubRepo
    notifier: Notifier
    identity: IdentityProvider
    kits: KitRepo
    wanted: WantedRepo
    tool_id: ToolIdentifier


_container: Container | None = None


def build_container(settings: Settings) -> Container:
    if settings.env == "prod":
        from google.cloud import firestore

        from .repos.firestore import (
            FirestoreBookingRepo,
            FirestoreKitRepo,
            FirestoreListingRepo,
            FirestoreMessageRepo,
            FirestoreNotificationRepo,
            FirestorePushSubRepo,
            FirestoreReportRepo,
            FirestoreReviewRepo,
            FirestoreUserRepo,
            FirestoreWantedRepo,
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
            reports=FirestoreReportRepo(db),
            payments=payments,
            planner=build_planner(settings.env, settings.anthropic_api_key,
                                  settings.planner, settings.gcp_project,
                                  settings.gemini_model),
            tasks=tasks,
            photos=GcsPhotoStore(settings.photos_bucket)
            if settings.photos_bucket else MemoryPhotoStore(),
            google_auth=build_verifier(settings.env, settings.google_client_id),
            notifications=(notif_repo := FirestoreNotificationRepo(db)),
            push_subs=(subs_repo := FirestorePushSubRepo(db)),
            notifier=Notifier(notif_repo, subs_repo,
                              settings.vapid_private_key, settings.vapid_subject),
            identity=StripeIdentity(settings.stripe_secret_key, settings.service_base_url)
            if settings.stripe_secret_key else FakeIdentity(),
            kits=FirestoreKitRepo(db),
            wanted=FirestoreWantedRepo(db),
            tool_id=build_identifier(settings.planner, settings.gcp_project,
                                     settings.gemini_model),
        )

    from .repos.memory import (
        MemoryBookingRepo,
        MemoryKitRepo,
        MemoryListingRepo,
        MemoryMessageRepo,
        MemoryNotificationRepo,
        MemoryPushSubRepo,
        MemoryReportRepo,
        MemoryReviewRepo,
        MemoryUserRepo,
        MemoryWantedRepo,
    )

    return Container(
        users=MemoryUserRepo(),
        listings=MemoryListingRepo(),
        bookings=MemoryBookingRepo(),
        messages=MemoryMessageRepo(),
        reviews=MemoryReviewRepo(),
        reports=MemoryReportRepo(),
        payments=FakePayments(),
        planner=build_planner(settings.env, settings.anthropic_api_key,
                                  settings.planner, settings.gcp_project,
                                  settings.gemini_model),
        tasks=FakeScheduler(),
        photos=MemoryPhotoStore(),
        google_auth=build_verifier(settings.env, settings.google_client_id),
        notifications=(notif_repo := MemoryNotificationRepo()),
        push_subs=(subs_repo := MemoryPushSubRepo()),
        notifier=Notifier(notif_repo, subs_repo,
                          settings.vapid_private_key, settings.vapid_subject),
        identity=FakeIdentity(),
        kits=MemoryKitRepo(),
        wanted=MemoryWantedRepo(),
        tool_id=build_identifier(settings.planner, settings.gcp_project,
                                 settings.gemini_model),
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
