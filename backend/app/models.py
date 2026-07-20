from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ToolCategory(str, enum.Enum):
    POWER_TOOLS = "power_tools"
    HAND_TOOLS = "hand_tools"
    GARDEN = "garden"
    LADDERS_ACCESS = "ladders_access"
    PAINTING_DECORATING = "painting_decorating"
    PLUMBING = "plumbing"
    AUTOMOTIVE = "automotive"
    CLEANING = "cleaning"
    MEASURING = "measuring"
    OTHER = "other"


class ListingStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    REMOVED = "removed"


class BookingState(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"  # lender said yes; payment in flight
    CONFIRMED = "confirmed"  # rental charged, deposit held
    PICKED_UP = "picked_up"
    RETURNED = "returned"
    COMPLETED = "completed"  # payout released
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED_BY_BORROWER = "cancelled_by_borrower"
    CANCELLED_BY_LENDER = "cancelled_by_lender"
    DISPUTED = "disputed"


TERMINAL_STATES = {
    BookingState.COMPLETED,
    BookingState.DECLINED,
    BookingState.EXPIRED,
    BookingState.CANCELLED_BY_BORROWER,
    BookingState.CANCELLED_BY_LENDER,
}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    uid: str
    display_name: str = ""
    email: str = ""  # from Google Sign-In; never shown on public profiles
    photo_url: str = ""
    bio: str = ""
    phone_verified: bool = False
    stripe_customer_id: str = ""
    stripe_connect_id: str = ""
    # Card-on-file is required before requesting any rental — the identity
    # anchor and deposit-hold guarantee that keeps both sides safe.
    card_on_file: bool = False
    card_last4: str = ""
    id_verified: bool = False  # government-ID check (Stripe Identity in prod)
    # Referral program: give $10, get $10. The inviter is paid when the
    # invited neighbor's first rental confirms (not at signup — gaming filter).
    credit_cents: int = 0
    referred_by: str = ""
    referral_paid: bool = False
    favorites: list[str] = Field(default_factory=list)  # listing ids, capped
    rating_avg: float = 0.0
    rating_count: int = 0
    created_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=80)
    photo_url: Optional[str] = None
    bio: Optional[str] = Field(default=None, max_length=300)


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

class ListingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    category: ToolCategory
    description: str = Field(default="", max_length=2000)
    condition: str = Field(default="good", max_length=40)
    photos: list[str] = Field(default_factory=list, max_length=8)
    price_per_day_cents: int = Field(ge=500, le=50_000)
    # Optional weekly rate: rentals of 7+ days price as weeks + leftover days,
    # never more than the plain daily total.
    price_per_week_cents: int = Field(default=0, ge=0, le=300_000)
    deposit_cents: int = Field(default=0, ge=0, le=200_000)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    exact_address: str = Field(default="", max_length=300)
    instant_book: bool = False  # ID-verified borrowers skip the approval wait

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()


class ListingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    condition: Optional[str] = None
    photos: Optional[list[str]] = None
    price_per_day_cents: Optional[int] = Field(default=None, ge=500, le=50_000)
    price_per_week_cents: Optional[int] = Field(default=None, ge=0, le=300_000)
    deposit_cents: Optional[int] = Field(default=None, ge=0, le=200_000)
    status: Optional[ListingStatus] = None
    blackout_dates: Optional[list[date]] = Field(default=None, max_length=180)
    instant_book: Optional[bool] = None


class Listing(BaseModel):
    id: str
    owner_uid: str
    title: str
    category: ToolCategory
    description: str = ""
    condition: str = "good"
    photos: list[str] = Field(default_factory=list)
    price_per_day_cents: int
    price_per_week_cents: int = 0
    deposit_cents: int = 0
    geohash: str = ""
    # Jittered coordinates safe for public display; exact address is only
    # ever exposed through the booking detail endpoint after confirmation.
    approx_lat: float = 0.0
    approx_lng: float = 0.0
    status: ListingStatus = ListingStatus.ACTIVE
    instant_book: bool = False
    # Days the owner has blocked out (vacations, own use); bookings can't
    # overlap these and the calendar shows them as unavailable.
    blackout_dates: list[date] = Field(default_factory=list)
    rating_avg: float = 0.0
    rating_count: int = 0
    created_at: Optional[datetime] = None


class ListingSearchResult(BaseModel):
    listing: Listing
    distance_km: float


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

class PriceBreakdown(BaseModel):
    days: int
    price_per_day_cents: int
    rental_cents: int
    service_fee_cents: int
    # ToolShare Guarantee: flat per-rental protection line funding coverage
    # up to the guarantee cap (see Settings.guarantee_cap_cents).
    protection_fee_cents: int = 0
    total_cents: int
    deposit_cents: int
    currency: str = "usd"


class BookingCreate(BaseModel):
    listing_id: str
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be on or after start_date")
        return v


class TimelineEvent(BaseModel):
    at: datetime
    actor_uid: str  # "system" for automated transitions
    from_state: Optional[BookingState] = None
    to_state: BookingState
    note: str = ""


class Booking(BaseModel):
    id: str
    listing_id: str
    listing_title: str = ""
    borrower_uid: str
    lender_uid: str
    start_date: date
    end_date: date
    state: BookingState = BookingState.REQUESTED
    price: PriceBreakdown
    stripe_payment_intent: str = ""
    stripe_deposit_intent: str = ""
    stripe_transfer_id: str = ""
    credit_applied_cents: int = 0  # referral credit consumed by this booking
    borrower_marked_pickup: bool = False
    lender_marked_pickup: bool = False
    # Condition documentation: photos at handoff and return, plus the AI
    # before/after comparison — makes guarantee claims adjudicable.
    pickup_photos: list[str] = Field(default_factory=list)
    return_photos: list[str] = Field(default_factory=list)
    damage_verdict: str = ""  # "" | ok | damage_suspected | inconclusive
    damage_notes: str = ""
    exact_address: str = ""  # populated only for participants once CONFIRMED
    timeline: list[TimelineEvent] = Field(default_factory=list)
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Chat & reviews
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class Message(BaseModel):
    id: str
    booking_id: str
    sender_uid: str
    text: str
    created_at: Optional[datetime] = None


class ReportCreate(BaseModel):
    target_type: str = Field(pattern="^(listing|user|booking)$")
    target_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5, max_length=2000)


class Report(BaseModel):
    id: str
    reporter_uid: str
    target_type: str
    target_id: str
    reason: str
    created_at: Optional[datetime] = None


class KitItemSnapshot(BaseModel):
    """A tool slot in a saved kit, frozen at plan time for the public page."""

    name: str
    category: ToolCategory
    why: str = ""
    optional: bool = False
    listing_id: str = ""  # best match at plan time ("" = gap)
    listing_title: str = ""
    price_per_day_cents: int = 0
    distance_km: float = 0.0


class Kit(BaseModel):
    id: str
    owner_uid: str
    description: str
    summary: str
    items: list[KitItemSnapshot]
    missing: list[str] = Field(default_factory=list)
    total_per_day_cents: int = 0
    buy_estimate_cents: int = 0  # what buying all this would roughly cost
    geohash: str = ""  # 5-char neighborhood prefix
    guide: Optional[dict] = None  # cached AI build guide (services.guides)
    created_at: Optional[datetime] = None


class SavedSearch(BaseModel):
    """A borrower's standing alert: notify me when this gets listed nearby."""

    id: str
    uid: str
    term: str
    geohash: str  # 5-char neighborhood prefix
    created_at: Optional[datetime] = None


class WantedSignal(BaseModel):
    """Unmet demand: an unmatched search or a kit gap, localized by geohash."""

    id: str
    geohash: str  # 5-char neighborhood prefix
    term: str
    source: str = "search"  # search | kit
    uid: str = ""
    created_at: Optional[datetime] = None


class Notification(BaseModel):
    id: str
    uid: str  # recipient
    kind: str = "booking"  # booking | message | payout | system
    title: str
    body: str = ""
    booking_id: str = ""
    read: bool = False
    created_at: Optional[datetime] = None


class PushSubscription(BaseModel):
    """A browser Web Push subscription (endpoint + client keys)."""

    uid: str
    endpoint: str
    p256dh: str
    auth: str


class ReviewCreate(BaseModel):
    stars: int = Field(ge=1, le=5)
    text: str = Field(default="", max_length=1000)


class Review(BaseModel):
    id: str
    booking_id: str
    from_uid: str
    to_uid: str
    stars: int
    text: str = ""
    created_at: Optional[datetime] = None
