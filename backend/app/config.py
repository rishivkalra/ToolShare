from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App configuration, read from environment variables.

    On Cloud Run, set these via `gcloud run deploy --set-env-vars` or secrets.
    ENV=dev enables the in-memory repos and fake payment provider so the API
    runs locally with no GCP or Stripe credentials.
    """

    env: str = "dev"  # dev | prod
    gcp_project: str = ""
    firestore_database: str = "(default)"
    photos_bucket: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Enables the Claude-backed project planner. Empty in dev = keyword fake.
    anthropic_api_key: str = ""

    # Borrower-side service fee.
    service_fee_pct: float = 0.15
    service_fee_min_cents: int = 100
    min_price_per_day_cents: int = 500

    # Booking requests expire if the lender doesn't respond.
    request_expiry_hours: int = 24
    # Deposit holds are voided this long after a clean return.
    deposit_void_hours: int = 24

    # Cloud Tasks queue for delayed jobs (request expiry, deposit void).
    tasks_queue: str = ""
    tasks_location: str = "us-central1"
    service_base_url: str = ""  # public URL of this service, for task callbacks
    # Shared secret for /internal/tasks/* handlers; empty in dev = check skipped.
    internal_task_secret: str = ""

    # Dev-only: bearer token accepted as "user:<uid>" without Firebase.
    dev_auth_enabled: bool = True

    model_config = {"env_prefix": "TOOLSHARE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
