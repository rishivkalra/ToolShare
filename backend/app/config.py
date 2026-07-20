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

    # Project-planner backend: "auto" (Claude if key set, else keyword fake),
    # "gemini" (Vertex AI via the service's own GCP identity — no key needed),
    # or "claude".
    planner: str = "auto"
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""

    # Borrower-side service fee.
    service_fee_pct: float = 0.15
    service_fee_min_cents: int = 100
    min_price_per_day_cents: int = 500

    # ToolShare Guarantee: flat protection line on every rental, funding
    # damage/theft coverage up to the cap (self-underwritten at launch).
    protection_fee_cents: int = 150
    guarantee_cap_cents: int = 250_000

    # Web Push (VAPID). Generated once by gcp_provision.py; empty disables
    # push (in-app notifications still work).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:support@toolshare.app"

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

    # Accept "dev:<uid>" bearer tokens without Firebase. None = auto (enabled
    # only when env=dev). Set explicitly to true for a staging deploy and to
    # false at public launch.
    dev_auth_enabled: bool | None = None

    # Google Sign-In (web landing page). The OAuth 2.0 Web client id from the
    # Cloud Console credentials page; empty disables the Google button.
    google_client_id: str = ""
    # Signs first-party session tokens; falls back to the internal task secret
    # so staging needs no extra config. Rotating it signs everyone out.
    session_secret: str = ""

    @property
    def session_signing_key(self) -> str:
        return self.session_secret or self.internal_task_secret or "toolshare-dev-sessions"

    @property
    def dev_auth_active(self) -> bool:
        if self.dev_auth_enabled is None:
            return self.env == "dev"
        return self.dev_auth_enabled

    model_config = {"env_prefix": "TOOLSHARE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
