"""In-memory repositories for local dev and tests."""
from __future__ import annotations

import itertools
import threading
from datetime import date
from typing import Optional

from ..models import (
    Booking,
    BookingState,
    Listing,
    Message,
    Review,
    TERMINAL_STATES,
    UserProfile,
)

_counter = itertools.count(1)
_lock = threading.Lock()


def next_id(prefix: str) -> str:
    with _lock:
        return f"{prefix}_{next(_counter):06d}"


class MemoryUserRepo:
    def __init__(self):
        self.users: dict[str, UserProfile] = {}

    def get(self, uid: str) -> Optional[UserProfile]:
        return self.users.get(uid)

    def upsert(self, user: UserProfile) -> UserProfile:
        self.users[user.uid] = user
        return user


class MemoryListingRepo:
    def __init__(self):
        self.listings: dict[str, Listing] = {}
        self.addresses: dict[str, str] = {}

    def get(self, listing_id: str) -> Optional[Listing]:
        return self.listings.get(listing_id)

    def create(self, listing: Listing) -> Listing:
        self.listings[listing.id] = listing
        return listing

    def update(self, listing: Listing) -> Listing:
        self.listings[listing.id] = listing
        return listing

    def by_owner(self, owner_uid: str) -> list[Listing]:
        return [l for l in self.listings.values() if l.owner_uid == owner_uid]

    def by_geohash_prefixes(self, prefixes: list[str], limit: int = 200) -> list[Listing]:
        out = [
            l
            for l in self.listings.values()
            if any(l.geohash.startswith(p) for p in prefixes)
        ]
        return out[:limit]

    def get_exact_address(self, listing_id: str) -> str:
        return self.addresses.get(listing_id, "")

    def set_exact_address(self, listing_id: str, address: str) -> None:
        self.addresses[listing_id] = address


class MemoryBookingRepo:
    def __init__(self):
        self.bookings: dict[str, Booking] = {}

    def get(self, booking_id: str) -> Optional[Booking]:
        return self.bookings.get(booking_id)

    def create(self, booking: Booking) -> Booking:
        self.bookings[booking.id] = booking
        return booking

    def update(self, booking: Booking) -> Booking:
        self.bookings[booking.id] = booking
        return booking

    def for_user(self, uid: str) -> list[Booking]:
        return [
            b
            for b in self.bookings.values()
            if uid in (b.borrower_uid, b.lender_uid)
        ]

    def overlapping(self, listing_id: str, start: date, end: date) -> list[Booking]:
        blocking = {BookingState.CONFIRMED, BookingState.PICKED_UP, BookingState.APPROVED}
        return [
            b
            for b in self.bookings.values()
            if b.listing_id == listing_id
            and b.state in blocking
            and b.start_date <= end
            and b.end_date >= start
        ]


class MemoryMessageRepo:
    def __init__(self):
        self.messages: list[Message] = []

    def create(self, message: Message) -> Message:
        self.messages.append(message)
        return message

    def for_booking(self, booking_id: str, limit: int = 100) -> list[Message]:
        return [m for m in self.messages if m.booking_id == booking_id][-limit:]


class MemoryReviewRepo:
    def __init__(self):
        self.reviews: list[Review] = []

    def create(self, review: Review) -> Review:
        self.reviews.append(review)
        return review

    def for_user(self, uid: str) -> list[Review]:
        return [r for r in self.reviews if r.to_uid == uid]

    def for_booking_from(self, booking_id: str, from_uid: str) -> Optional[Review]:
        for r in self.reviews:
            if r.booking_id == booking_id and r.from_uid == from_uid:
                return r
        return None
