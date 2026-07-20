"""Saved searches: "tell me when a neighbor lists one"."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import geo
from ..auth import current_uid
from ..deps import Container, get_container
from ..models import SavedSearch
from ..repos.memory import next_id

router = APIRouter(prefix="/v1/searches", tags=["searches"])


class SavedSearchCreate(BaseModel):
    term: str = Field(min_length=3, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.post("", response_model=SavedSearch, status_code=201)
def save_search(
    body: SavedSearchCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    existing = c.saved_searches.for_user(uid)
    term = body.term.strip().lower()
    for s in existing:
        if s.term == term:
            return s  # idempotent
    if len(existing) >= 20:
        raise HTTPException(status_code=400, detail="Saved-search limit reached (20)")
    return c.saved_searches.create(SavedSearch(
        id=next_id("sav"), uid=uid, term=term,
        geohash=geo.encode(body.lat, body.lng)[:5],
        created_at=datetime.now(timezone.utc),
    ))


@router.get("", response_model=list[SavedSearch])
def my_searches(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    return c.saved_searches.for_user(uid)


@router.delete("/{search_id}", status_code=204)
def delete_search(
    search_id: str,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    if not c.saved_searches.delete(search_id, uid):
        raise HTTPException(status_code=404, detail="Saved search not found")
