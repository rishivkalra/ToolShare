from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from .. import geo
from ..auth import current_uid
from ..deps import Container, get_container
from ..models import (
    BookingState,
    Listing,
    ListingCreate,
    ListingSearchResult,
    ListingStatus,
    ListingUpdate,
    ToolCategory,
)
from ..models import WantedSignal
from ..pricing import rental_days
from ..repos.memory import next_id
from ..services.photos import MAX_PHOTO_BYTES
from ..services.tool_id import ToolIdSuggestion

router = APIRouter(prefix="/v1/listings", tags=["listings"])
photos_router = APIRouter(prefix="/v1/photos", tags=["listings"])


@router.post("", response_model=Listing, status_code=201)
def create_listing(
    body: ListingCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    approx_lat, approx_lng = geo.jitter(body.lat, body.lng)
    listing = Listing(
        id=next_id("lst"),
        owner_uid=uid,
        title=body.title,
        category=body.category,
        description=body.description,
        condition=body.condition,
        photos=body.photos,
        price_per_day_cents=body.price_per_day_cents,
        price_per_week_cents=body.price_per_week_cents,
        deposit_cents=body.deposit_cents,
        geohash=geo.encode(body.lat, body.lng),
        approx_lat=approx_lat,
        approx_lng=approx_lng,
        instant_book=body.instant_book,
        created_at=datetime.now(timezone.utc),
    )
    c.listings.create(listing)
    if body.exact_address:
        c.listings.set_exact_address(listing.id, body.exact_address)

    # Saved-search alerts: neighbors waiting for exactly this get pinged now.
    title_words = set(listing.title.lower().replace("-", " ").split())
    for s in c.saved_searches.for_geohash(listing.geohash[:5]):
        if s.uid == uid:
            continue
        needle_words = set(s.term.lower().split())
        if s.term.lower() in listing.title.lower() or needle_words <= title_words:
            c.notifier.notify(
                s.uid,
                f"🔔 A neighbor just listed: {listing.title}",
                f"You asked to hear about “{s.term}” — it's now "
                f"${listing.price_per_day_cents / 100:.0f}/day nearby.",
                kind="system",
            )
    return listing


@router.get("/search", response_model=list[ListingSearchResult])
def search(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=5.0, gt=0, le=50),
    category: ToolCategory | None = None,
    q: str = "",
    c: Container = Depends(get_container),
):
    prefixes = geo.cover_prefixes(lat, lng, radius_km)
    candidates = c.listings.by_geohash_prefixes(prefixes)
    results: list[ListingSearchResult] = []
    needle = q.strip().lower()
    for l in candidates:
        if l.status != ListingStatus.ACTIVE:
            continue
        if category and l.category != category:
            continue
        if needle and needle not in l.title.lower() and needle not in l.description.lower():
            continue
        dist = geo.haversine_km(lat, lng, l.approx_lat, l.approx_lng)
        if dist <= radius_km:
            results.append(ListingSearchResult(listing=l, distance_km=round(dist, 2)))
    results.sort(key=lambda r: r.distance_km)
    # Live availability on cards: is the tool out on a rental *today*?
    today = datetime.now(timezone.utc).date()
    for r in results[:60]:
        active = [
            b.end_date
            for b in c.bookings.by_listing(r.listing.id)
            if b.state in _BLOCKING_STATES and b.start_date <= today <= b.end_date
        ]
        if active:
            r.rented_until = max(active)
    if needle and not results and len(needle) >= 3:
        # Unmet demand is a supply signal: nearby owners get a weekly
        # "wanted near you" digest built from these.
        c.wanted.create(WantedSignal(
            id=next_id("wnt"), geohash=geo.encode(lat, lng)[:5],
            term=needle[:60], source="search",
            created_at=datetime.now(timezone.utc),
        ))
    return results


class PriceSuggestion(BaseModel):
    category: ToolCategory
    suggested_per_day_cents: int
    based_on: int  # nearby same-category listings used ("0" = category default)


_CATEGORY_DEFAULT_CENTS = {
    ToolCategory.POWER_TOOLS: 900, ToolCategory.HAND_TOOLS: 500,
    ToolCategory.GARDEN: 700, ToolCategory.LADDERS_ACCESS: 600,
    ToolCategory.PAINTING_DECORATING: 600, ToolCategory.PLUMBING: 700,
    ToolCategory.AUTOMOTIVE: 900, ToolCategory.CLEANING: 1100,
    ToolCategory.MEASURING: 500, ToolCategory.OTHER: 700,
}


@router.get("/price-suggestion", response_model=PriceSuggestion)
def price_suggestion(
    category: ToolCategory,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    c: Container = Depends(get_container),
):
    """Fair-price hint from what the same category actually rents for nearby;
    falls back to category defaults when the neighborhood is thin."""
    prefixes = geo.cover_prefixes(lat, lng, 8.0)
    prices = sorted(
        l.price_per_day_cents
        for l in c.listings.by_geohash_prefixes(prefixes)
        if l.status == ListingStatus.ACTIVE and l.category == category
    )
    if len(prices) >= 3:
        return PriceSuggestion(category=category,
                               suggested_per_day_cents=prices[len(prices) // 2],
                               based_on=len(prices))
    return PriceSuggestion(category=category,
                           suggested_per_day_cents=_CATEGORY_DEFAULT_CENTS[category],
                           based_on=len(prices))


@router.post("/identify", response_model=ToolIdSuggestion)
async def identify_tool(
    file: UploadFile,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Photo-to-listing: one photo in, a drafted listing out (Gemini vision).
    The client prefills the form with this; the owner stays in control."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only images are accepted")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large (max 5MB)")
    try:
        return c.tool_id.identify(data, file.content_type or "image/jpeg")
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't identify the tool — fill the form manually")


@router.get("/mine", response_model=list[Listing])
def my_listings(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    return c.listings.by_owner(uid)


@router.get("/{listing_id}", response_model=Listing)
def get_listing(listing_id: str, c: Container = Depends(get_container)):
    listing = c.listings.get(listing_id)
    if not listing or listing.status == ListingStatus.REMOVED:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("/{listing_id}/photo", response_model=Listing)
async def upload_photo(
    listing_id: str,
    file: UploadFile,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Attach a photo to a listing (owner only, max 8 photos, 5MB each)."""
    listing = c.listings.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.owner_uid != uid:
        raise HTTPException(status_code=403, detail="Not your listing")
    if len(listing.photos) >= 8:
        raise HTTPException(status_code=400, detail="Photo limit reached (8)")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only images are accepted")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large (max 5MB)")
    url = c.photos.save(data, file.content_type)
    listing.photos.append(url)
    return c.listings.update(listing)


class BookedRange(BaseModel):
    start_date: date
    end_date: date


class Availability(BaseModel):
    listing_id: str
    booked: list[BookedRange]
    blackout_dates: list[date]


_BLOCKING_STATES = {BookingState.APPROVED, BookingState.CONFIRMED, BookingState.PICKED_UP}


@router.get("/{listing_id}/availability", response_model=Availability)
def availability(listing_id: str, c: Container = Depends(get_container)):
    """Public calendar data: booked ranges + owner blackout days (no borrower
    identities are exposed)."""
    listing = c.listings.get(listing_id)
    if not listing or listing.status == ListingStatus.REMOVED:
        raise HTTPException(status_code=404, detail="Listing not found")
    today = datetime.now(timezone.utc).date()
    booked = [
        BookedRange(start_date=b.start_date, end_date=b.end_date)
        for b in c.bookings.by_listing(listing_id)
        if b.state in _BLOCKING_STATES and b.end_date >= today
    ]
    booked.sort(key=lambda r: r.start_date)
    return Availability(
        listing_id=listing_id,
        booked=booked,
        blackout_dates=sorted(d for d in listing.blackout_dates if d >= today),
    )


class RentalHistoryEntry(BaseModel):
    booking_id: str
    borrower_uid: str
    borrower_name: str
    start_date: date
    end_date: date
    days: int
    state: BookingState
    earned_cents: int


class RentalHistory(BaseModel):
    listing_id: str
    title: str
    times_rented: int
    total_days_rented: int
    total_earned_cents: int
    active_borrower: str = ""  # who has it right now, if anyone
    active_until: date | None = None
    entries: list[RentalHistoryEntry]


_EARNING_STATES = {BookingState.CONFIRMED, BookingState.PICKED_UP,
                   BookingState.RETURNED, BookingState.COMPLETED, BookingState.DISPUTED}


@router.get("/{listing_id}/history", response_model=RentalHistory)
def rental_history(
    listing_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    """Owner-only rental log: who rented this tool, for how long, and earnings."""
    listing = c.listings.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.owner_uid != uid:
        raise HTTPException(status_code=403, detail="Not your listing")

    entries: list[RentalHistoryEntry] = []
    active_borrower, active_until = "", None
    for b in sorted(c.bookings.by_listing(listing_id),
                    key=lambda x: x.start_date, reverse=True):
        if b.state not in _EARNING_STATES:
            continue
        borrower = c.users.get(b.borrower_uid)
        name = (borrower.display_name if borrower and borrower.display_name
                else b.borrower_uid)
        days = rental_days(b.start_date, b.end_date)
        entries.append(RentalHistoryEntry(
            booking_id=b.id, borrower_uid=b.borrower_uid, borrower_name=name,
            start_date=b.start_date, end_date=b.end_date, days=days,
            state=b.state, earned_cents=b.price.rental_cents,
        ))
        if b.state in (BookingState.CONFIRMED, BookingState.PICKED_UP):
            active_borrower, active_until = name, b.end_date

    return RentalHistory(
        listing_id=listing_id,
        title=listing.title,
        times_rented=len(entries),
        total_days_rented=sum(e.days for e in entries),
        total_earned_cents=sum(e.earned_cents for e in entries),
        active_borrower=active_borrower,
        active_until=active_until,
        entries=entries,
    )


@photos_router.get("/{name}", include_in_schema=False)
def serve_photo(name: str, c: Container = Depends(get_container)):
    """Serves photos in dev (prod photos live on a public GCS bucket)."""
    blob = c.photos.get(name)
    if not blob:
        raise HTTPException(status_code=404, detail="Photo not found")
    data, content_type = blob
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=31536000"})


class FavoriteResponse(BaseModel):
    favorited: bool
    count: int


@router.put("/{listing_id}/favorite", response_model=FavoriteResponse)
def toggle_favorite(
    listing_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    from ..models import UserProfile

    if not c.listings.get(listing_id):
        raise HTTPException(status_code=404, detail="Listing not found")
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    if listing_id in user.favorites:
        user.favorites.remove(listing_id)
        favorited = False
    else:
        user.favorites = (user.favorites + [listing_id])[-100:]
        favorited = True
    c.users.upsert(user)
    return FavoriteResponse(favorited=favorited, count=len(user.favorites))


@router.patch("/{listing_id}", response_model=Listing)
def update_listing(
    listing_id: str,
    body: ListingUpdate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    listing = c.listings.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.owner_uid != uid:
        raise HTTPException(status_code=403, detail="Not your listing")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(listing, k, v)
    return c.listings.update(listing)
