from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_uid
from ..deps import Container, get_container
from ..models import BookingState, Review, ReviewCreate
from ..repos.memory import next_id

router = APIRouter(prefix="/v1", tags=["reviews"])


@router.post("/bookings/{booking_id}/reviews", response_model=Review, status_code=201)
def leave_review(
    booking_id: str,
    body: ReviewCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    booking = c.bookings.get(booking_id)
    if not booking or uid not in (booking.borrower_uid, booking.lender_uid):
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.state not in (BookingState.COMPLETED, BookingState.DISPUTED):
        raise HTTPException(status_code=409, detail="Booking not finished yet")
    if c.reviews.for_booking_from(booking_id, uid):
        raise HTTPException(status_code=409, detail="Already reviewed")

    to_uid = booking.lender_uid if uid == booking.borrower_uid else booking.borrower_uid
    review = Review(
        id=next_id("rev"),
        booking_id=booking_id,
        from_uid=uid,
        to_uid=to_uid,
        stars=body.stars,
        text=body.text,
        created_at=datetime.now(timezone.utc),
    )
    c.reviews.create(review)

    # Refresh the target's denormalized rating snapshot.
    target = c.users.get(to_uid)
    if target:
        all_reviews = c.reviews.for_user(to_uid)
        target.rating_count = len(all_reviews)
        target.rating_avg = round(sum(r.stars for r in all_reviews) / len(all_reviews), 2)
        c.users.upsert(target)

    # And the listing's, when the borrower reviewed the lender's tool.
    if uid == booking.borrower_uid:
        listing = c.listings.get(booking.listing_id)
        if listing:
            n, avg = listing.rating_count, listing.rating_avg
            listing.rating_avg = round((avg * n + body.stars) / (n + 1), 2)
            listing.rating_count = n + 1
            c.listings.update(listing)

    return review


@router.get("/users/{uid}/reviews", response_model=list[Review])
def user_reviews(uid: str, c: Container = Depends(get_container)):
    return c.reviews.for_user(uid)
