"""Firestore-backed repositories (production).

Collections:
  users/{uid}
  listings/{id}                      (public fields only)
  listing_private/{id}               (exact_address — never in public payloads)
  bookings/{id}
  bookings/{id}/messages/{mid}
  reviews/{id}

Only imported when TOOLSHARE_ENV=prod, so local dev needs no GCP creds.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from google.cloud import firestore

from ..models import (
    Booking,
    BookingState,
    Kit,
    Listing,
    Message,
    Notification,
    PushSubscription,
    Report,
    Review,
    SavedSearch,
    UserProfile,
    WantedSignal,
)


def _doc_to(model_cls, doc):
    if not doc.exists:
        return None
    data = doc.to_dict()
    data["id"] = doc.id
    return model_cls.model_validate(data)


class FirestoreUserRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("users")

    def get(self, uid: str) -> Optional[UserProfile]:
        doc = self.col.document(uid).get()
        if not doc.exists:
            return None
        return UserProfile.model_validate({**doc.to_dict(), "uid": doc.id})

    def upsert(self, user: UserProfile) -> UserProfile:
        self.col.document(user.uid).set(user.model_dump(exclude={"uid"}, mode="json"))
        return user


class FirestoreListingRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("listings")
        self.private = db.collection("listing_private")

    def get(self, listing_id: str) -> Optional[Listing]:
        return _doc_to(Listing, self.col.document(listing_id).get())

    def create(self, listing: Listing) -> Listing:
        self.col.document(listing.id).set(listing.model_dump(exclude={"id"}, mode="json"))
        return listing

    def update(self, listing: Listing) -> Listing:
        return self.create(listing)

    def by_owner(self, owner_uid: str) -> list[Listing]:
        docs = self.col.where("owner_uid", "==", owner_uid).stream()
        return [_doc_to(Listing, d) for d in docs]

    def by_geohash_prefixes(self, prefixes: list[str], limit: int = 200) -> list[Listing]:
        out: list[Listing] = []
        for p in prefixes:
            docs = (
                self.col.where("status", "==", "active")
                .where("geohash", ">=", p)
                .where("geohash", "<", p + "\uf8ff")
                .limit(limit)
                .stream()
            )
            out.extend(_doc_to(Listing, d) for d in docs)
        return out[:limit]

    def get_exact_address(self, listing_id: str) -> str:
        doc = self.private.document(listing_id).get()
        return (doc.to_dict() or {}).get("exact_address", "") if doc.exists else ""

    def set_exact_address(self, listing_id: str, address: str) -> None:
        self.private.document(listing_id).set({"exact_address": address})


class FirestoreBookingRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("bookings")

    def get(self, booking_id: str) -> Optional[Booking]:
        return _doc_to(Booking, self.col.document(booking_id).get())

    def create(self, booking: Booking) -> Booking:
        self.col.document(booking.id).set(booking.model_dump(exclude={"id"}, mode="json"))
        return booking

    def update(self, booking: Booking) -> Booking:
        return self.create(booking)

    def for_user(self, uid: str) -> list[Booking]:
        out = []
        for field in ("borrower_uid", "lender_uid"):
            docs = self.col.where(field, "==", uid).stream()
            out.extend(_doc_to(Booking, d) for d in docs)
        return out

    def by_listing(self, listing_id: str) -> list[Booking]:
        docs = self.col.where("listing_id", "==", listing_id).stream()
        return [_doc_to(Booking, d) for d in docs]

    def overlapping(self, listing_id: str, start: date, end: date) -> list[Booking]:
        blocking = [
            BookingState.APPROVED.value,
            BookingState.CONFIRMED.value,
            BookingState.PICKED_UP.value,
        ]
        docs = (
            self.col.where("listing_id", "==", listing_id)
            .where("state", "in", blocking)
            .stream()
        )
        result = []
        for d in docs:
            b = _doc_to(Booking, d)
            if b.start_date <= end and b.end_date >= start:
                result.append(b)
        return result


class FirestoreMessageRepo:
    def __init__(self, db: firestore.Client):
        self.db = db

    def _col(self, booking_id: str):
        return self.db.collection("bookings").document(booking_id).collection("messages")

    def create(self, message: Message) -> Message:
        self._col(message.booking_id).document(message.id).set(
            message.model_dump(exclude={"id"}, mode="json")
        )
        return message

    def for_booking(self, booking_id: str, limit: int = 100) -> list[Message]:
        docs = self._col(booking_id).order_by("created_at").limit(limit).stream()
        return [_doc_to(Message, d) for d in docs]


class FirestoreReviewRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("reviews")

    def create(self, review: Review) -> Review:
        self.col.document(review.id).set(review.model_dump(exclude={"id"}, mode="json"))
        return review

    def for_user(self, uid: str) -> list[Review]:
        docs = self.col.where("to_uid", "==", uid).stream()
        return [_doc_to(Review, d) for d in docs]

    def for_booking_from(self, booking_id: str, from_uid: str) -> Optional[Review]:
        docs = (
            self.col.where("booking_id", "==", booking_id)
            .where("from_uid", "==", from_uid)
            .limit(1)
            .stream()
        )
        for d in docs:
            return _doc_to(Review, d)
        return None


class FirestoreReportRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("reports")

    def create(self, report: Report) -> Report:
        self.col.document(report.id).set(report.model_dump(exclude={"id"}, mode="json"))
        return report


class FirestoreKitRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("kits")

    def create(self, kit: Kit) -> Kit:
        self.col.document(kit.id).set(kit.model_dump(exclude={"id"}, mode="json"))
        return kit

    def get(self, kit_id: str):
        return _doc_to(Kit, self.col.document(kit_id).get())


class FirestoreWantedRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("wanted")

    def create(self, signal: WantedSignal) -> WantedSignal:
        self.col.document(signal.id).set(signal.model_dump(exclude={"id"}, mode="json"))
        return signal

    def since(self, cutoff_iso: str) -> list[WantedSignal]:
        # created_at is stored as an ISO string; lexicographic range works.
        docs = self.col.where("created_at", ">=", cutoff_iso).limit(2000).stream()
        return [_doc_to(WantedSignal, d) for d in docs]


class FirestoreSavedSearchRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("saved_searches")

    def create(self, search: SavedSearch) -> SavedSearch:
        self.col.document(search.id).set(search.model_dump(exclude={"id"}, mode="json"))
        return search

    def for_geohash(self, geohash: str) -> list[SavedSearch]:
        docs = self.col.where("geohash", "==", geohash).limit(500).stream()
        return [_doc_to(SavedSearch, d) for d in docs]

    def for_user(self, uid: str) -> list[SavedSearch]:
        docs = self.col.where("uid", "==", uid).limit(50).stream()
        return [_doc_to(SavedSearch, d) for d in docs]

    def delete(self, search_id: str, uid: str) -> bool:
        doc = self.col.document(search_id).get()
        if doc.exists and doc.to_dict().get("uid") == uid:
            doc.reference.delete()
            return True
        return False


class FirestoreNotificationRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("notifications")

    def create(self, notification: Notification) -> Notification:
        self.col.document(notification.id).set(
            notification.model_dump(exclude={"id"}, mode="json")
        )
        return notification

    def for_user(self, uid: str, limit: int = 50) -> list[Notification]:
        # Equality-only filter (no composite index needed); sort client-side.
        docs = self.col.where("uid", "==", uid).limit(200).stream()
        items = [_doc_to(Notification, d) for d in docs]
        items.sort(key=lambda n: n.created_at.isoformat() if n.created_at else "", reverse=True)
        return items[:limit]

    def mark_all_read(self, uid: str) -> int:
        count = 0
        for d in self.col.where("uid", "==", uid).where("read", "==", False).stream():
            d.reference.update({"read": True})
            count += 1
        return count


class FirestorePushSubRepo:
    def __init__(self, db: firestore.Client):
        self.col = db.collection("push_subs")

    @staticmethod
    def _key(uid: str, endpoint: str) -> str:
        import hashlib

        return f"{uid}_{hashlib.sha1(endpoint.encode()).hexdigest()[:16]}"

    def upsert(self, sub: PushSubscription) -> None:
        self.col.document(self._key(sub.uid, sub.endpoint)).set(sub.model_dump(mode="json"))

    def for_user(self, uid: str) -> list[PushSubscription]:
        docs = self.col.where("uid", "==", uid).stream()
        return [PushSubscription.model_validate(d.to_dict()) for d in docs]

    def remove(self, uid: str, endpoint: str) -> None:
        self.col.document(self._key(uid, endpoint)).delete()
