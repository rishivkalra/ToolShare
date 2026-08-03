"""The neighborhood wall: "built with borrowed tools" gratitude posts.

The BuyNothing/#ThankANeighbor retention lesson: finished-project photos and
thank-yous are the highest-engagement content a hyperlocal app can show.
Posting is earned — you need at least one completed rental — which keeps the
wall real and doubles as social proof that the marketplace works.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile

from .. import geo
from ..auth import current_uid
from ..deps import Container, get_container
from ..models import BookingState, ProjectPost
from ..repos.memory import next_id
from ..services.photos import MAX_PHOTO_BYTES
from ..services.ratelimit import rate_limit

router = APIRouter(prefix="/v1/posts", tags=["posts"])

_DONE_STATES = {BookingState.RETURNED, BookingState.COMPLETED}


@router.post("", response_model=ProjectPost, status_code=201,
             dependencies=[rate_limit("wall-post", 5)])
async def create_post(
    caption: str = Form(min_length=5, max_length=200),
    lat: float = Form(ge=-90, le=90),
    lng: float = Form(ge=-180, le=180),
    file: UploadFile | None = None,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    if not any(b.state in _DONE_STATES for b in c.bookings.for_user(uid)):
        raise HTTPException(
            status_code=403,
            detail="The wall is for finished projects — complete a rental first",
        )
    photo_url = ""
    if file is not None:
        if not (file.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Only images are accepted")
        data = await file.read()
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Photo too large (max 5MB)")
        photo_url = c.photos.save(data, file.content_type)

    user = c.users.get(uid)
    return c.posts.create(ProjectPost(
        id=next_id("pst"),
        uid=uid,
        author_name=(user.display_name if user and user.display_name else "A neighbor"),
        geohash=geo.encode(lat, lng)[:5],
        photo_url=photo_url,
        caption=caption.strip(),
        created_at=datetime.now(timezone.utc),
    ))


@router.get("", response_model=list[ProjectPost])
def wall(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    c: Container = Depends(get_container),
):
    return c.posts.for_geohash(geo.encode(lat, lng)[:5])
