from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import geo
from ..auth import current_uid
from ..deps import Container, get_container
from ..models import (
    Listing,
    ListingCreate,
    ListingSearchResult,
    ListingStatus,
    ListingUpdate,
    ToolCategory,
)
from ..repos.memory import next_id

router = APIRouter(prefix="/v1/listings", tags=["listings"])


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
        deposit_cents=body.deposit_cents,
        geohash=geo.encode(body.lat, body.lng),
        approx_lat=approx_lat,
        approx_lng=approx_lng,
        created_at=datetime.now(timezone.utc),
    )
    c.listings.create(listing)
    if body.exact_address:
        c.listings.set_exact_address(listing.id, body.exact_address)
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
    return results


@router.get("/mine", response_model=list[Listing])
def my_listings(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    return c.listings.by_owner(uid)


@router.get("/{listing_id}", response_model=Listing)
def get_listing(listing_id: str, c: Container = Depends(get_container)):
    listing = c.listings.get(listing_id)
    if not listing or listing.status == ListingStatus.REMOVED:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


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
