"""In-memory repositories for local dev and tests."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from ..models import (
    Booking,
    BookingState,
    ProjectPost,
    Kit,
    Listing,
    Message,
    Notification,
    PushSubscription,
    Report,
    Review,
    SavedSearch,
    TERMINAL_STATES,
    UserProfile,
    WantedSignal,
)

def next_id(prefix: str) -> str:
    # Random IDs: safe across processes and Cloud Run instances (a per-instance
    # counter would collide with existing Firestore documents).
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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

    def by_listing(self, listing_id: str) -> list[Booking]:
        return [b for b in self.bookings.values() if b.listing_id == listing_id]

    def by_state(self, state, limit: int = 100) -> list[Booking]:
        return [b for b in self.bookings.values() if b.state == state][:limit]

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


class MemoryReportRepo:
    def __init__(self):
        self.reports: list[Report] = []

    def create(self, report: Report) -> Report:
        self.reports.append(report)
        return report

    def recent(self, limit: int = 100) -> list[Report]:
        return list(reversed(self.reports))[:limit]


class MemoryNotificationRepo:
    def __init__(self):
        self.items: list[Notification] = []

    def create(self, notification: Notification) -> Notification:
        self.items.append(notification)
        return notification

    def for_user(self, uid: str, limit: int = 50) -> list[Notification]:
        mine = [n for n in self.items if n.uid == uid]
        mine.sort(key=lambda n: n.created_at or 0, reverse=True)
        return mine[:limit]

    def mark_all_read(self, uid: str) -> int:
        count = 0
        for n in self.items:
            if n.uid == uid and not n.read:
                n.read = True
                count += 1
        return count


class MemoryKitRepo:
    def __init__(self):
        self.kits: dict[str, Kit] = {}

    def create(self, kit: Kit) -> Kit:
        self.kits[kit.id] = kit
        return kit

    def get(self, kit_id: str) -> Optional[Kit]:
        return self.kits.get(kit_id)


class MemoryWantedRepo:
    def __init__(self):
        self.signals: list[WantedSignal] = []

    def create(self, signal: WantedSignal) -> WantedSignal:
        self.signals.append(signal)
        return signal

    def since(self, cutoff_iso: str) -> list[WantedSignal]:
        return [
            s for s in self.signals
            if s.created_at and s.created_at.isoformat() >= cutoff_iso
        ]


class MemoryPostRepo:
    def __init__(self):
        self.posts: list[ProjectPost] = []

    def create(self, post: ProjectPost) -> ProjectPost:
        self.posts.append(post)
        return post

    def for_geohash(self, geohash: str, limit: int = 12) -> list[ProjectPost]:
        mine = [p for p in self.posts if p.geohash == geohash]
        mine.sort(key=lambda p: p.created_at.isoformat() if p.created_at else "", reverse=True)
        return mine[:limit]


class MemorySavedSearchRepo:
    def __init__(self):
        self.searches: dict[str, SavedSearch] = {}

    def create(self, search: SavedSearch) -> SavedSearch:
        self.searches[search.id] = search
        return search

    def for_geohash(self, geohash: str) -> list[SavedSearch]:
        return [s for s in self.searches.values() if s.geohash == geohash]

    def for_user(self, uid: str) -> list[SavedSearch]:
        return [s for s in self.searches.values() if s.uid == uid]

    def delete(self, search_id: str, uid: str) -> bool:
        s = self.searches.get(search_id)
        if s and s.uid == uid:
            del self.searches[search_id]
            return True
        return False


class MemoryPushSubRepo:
    def __init__(self):
        self.subs: dict[tuple[str, str], PushSubscription] = {}

    def upsert(self, sub: PushSubscription) -> None:
        self.subs[(sub.uid, sub.endpoint)] = sub

    def for_user(self, uid: str) -> list[PushSubscription]:
        return [s for (u, _), s in self.subs.items() if u == uid]

    def remove(self, uid: str, endpoint: str) -> None:
        self.subs.pop((uid, endpoint), None)
