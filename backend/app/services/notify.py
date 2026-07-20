"""Notifications: in-app feed always; Web Push when VAPID keys are configured.

Web Push needs no third-party account — we sign requests with our own VAPID
keypair and browsers' push services (FCM, Mozilla autopush, APNs web) deliver
them. Dead subscriptions (404/410 from the push service) are pruned.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..models import Notification
from ..repos.base import NotificationRepo, PushSubRepo
from ..repos.memory import next_id

log = logging.getLogger(__name__)


class Notifier:
    def __init__(
        self,
        repo: NotificationRepo,
        subs: PushSubRepo,
        vapid_private_key: str = "",
        vapid_subject: str = "mailto:support@toolshare.app",
    ):
        self.repo = repo
        self.subs = subs
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject

    def notify(
        self, uid: str, title: str, body: str = "", booking_id: str = "", kind: str = "booking"
    ) -> Notification:
        n = self.repo.create(
            Notification(
                id=next_id("ntf"),
                uid=uid,
                kind=kind,
                title=title,
                body=body,
                booking_id=booking_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        self._push(uid, title, body)
        return n

    def _push(self, uid: str, title: str, body: str) -> None:
        if not self.vapid_private_key:
            return
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:  # keep dev/test environments light
            return
        payload = json.dumps({"title": title, "body": body, "url": "/app/#/rentals"})
        for sub in self.subs.for_user(uid):
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims={"sub": self.vapid_subject},
                    ttl=86400,
                )
            except WebPushException as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):
                    self.subs.remove(uid, sub.endpoint)
                else:
                    log.warning("web push failed for %s: %s", uid, e)
            except Exception as e:  # push must never break the request path
                log.warning("web push error for %s: %s", uid, e)
