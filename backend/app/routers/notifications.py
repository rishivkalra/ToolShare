"""In-app notification feed + Web Push subscription management."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import current_uid
from ..config import Settings, get_settings
from ..deps import Container, get_container
from ..models import Notification, PushSubscription

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class NotificationFeed(BaseModel):
    unread: int
    items: list[Notification]


@router.get("", response_model=NotificationFeed)
def feed(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    items = c.notifications.for_user(uid)
    return NotificationFeed(unread=sum(1 for n in items if not n.read), items=items)


class ReadResponse(BaseModel):
    marked: int


@router.post("/read", response_model=ReadResponse)
def mark_read(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    return ReadResponse(marked=c.notifications.mark_all_read(uid))


class PushConfig(BaseModel):
    vapid_public_key: str  # empty = web push disabled; in-app feed still works


@router.get("/config", response_model=PushConfig)
def push_config(settings: Settings = Depends(get_settings)):
    return PushConfig(vapid_public_key=settings.vapid_public_key)


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


@router.post("/subscriptions", status_code=201)
def subscribe(
    body: SubscribeBody,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    c.push_subs.upsert(
        PushSubscription(uid=uid, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth)
    )
    return {"ok": True}
