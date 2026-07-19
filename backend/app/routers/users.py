from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import current_uid
from ..deps import Container, get_container
from ..models import UserProfile, UserUpdate

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
def me(uid: str = Depends(current_uid), c: Container = Depends(get_container)):
    user = c.users.get(uid)
    if not user:
        user = c.users.upsert(
            UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
        )
    return user


@router.patch("/me", response_model=UserProfile)
def update_me(
    body: UserUpdate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    return c.users.upsert(user)


class ConnectLinkResponse(BaseModel):
    connect_account_id: str
    onboarding_url: str


@router.post("/me/connect", response_model=ConnectLinkResponse)
def start_connect_onboarding(
    uid: str = Depends(current_uid), c: Container = Depends(get_container)
):
    """Stripe Connect Express hosted onboarding so a lender can get paid.

    Triggered lazily — lenders can list tools first and onboard at their
    first approved booking.
    """
    user = c.users.get(uid) or UserProfile(uid=uid, created_at=datetime.now(timezone.utc))
    acct_id, url = c.payments.onboarding_link(uid, user.stripe_connect_id)
    if acct_id != user.stripe_connect_id:
        user.stripe_connect_id = acct_id
        c.users.upsert(user)
    return ConnectLinkResponse(connect_account_id=acct_id, onboarding_url=url)


@router.get("/{uid}", response_model=UserProfile)
def public_profile(uid: str, c: Container = Depends(get_container)):
    user = c.users.get(uid) or UserProfile(uid=uid)
    # Strip payment identifiers from public view.
    user.stripe_customer_id = ""
    user.stripe_connect_id = ""
    return user
