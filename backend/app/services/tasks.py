"""Delayed-job scheduling.

Prod: Google Cloud Tasks HTTP tasks posted back to this service's /internal/*
handlers. Dev/tests: an in-memory recorder so behavior is assertable without
GCP. Handlers must be idempotent — Cloud Tasks delivers at-least-once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class TaskScheduler(Protocol):
    def schedule(self, path: str, payload: dict, delay_seconds: int) -> None: ...


@dataclass
class ScheduledTask:
    path: str
    payload: dict
    delay_seconds: int


@dataclass
class FakeScheduler:
    tasks: list[ScheduledTask] = field(default_factory=list)

    def schedule(self, path: str, payload: dict, delay_seconds: int) -> None:
        self.tasks.append(ScheduledTask(path, payload, delay_seconds))


class CloudTasksScheduler:
    def __init__(self, project: str, location: str, queue: str, base_url: str, secret: str):
        import json

        from google.cloud import tasks_v2

        self._json = json
        self._tasks_v2 = tasks_v2
        self.client = tasks_v2.CloudTasksClient()
        self.parent = self.client.queue_path(project, location, queue)
        self.base_url = base_url.rstrip("/")
        self.secret = secret

    def schedule(self, path: str, payload: dict, delay_seconds: int) -> None:
        from datetime import datetime, timedelta, timezone

        from google.protobuf import timestamp_pb2

        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds))
        task = {
            "http_request": {
                "http_method": self._tasks_v2.HttpMethod.POST,
                "url": f"{self.base_url}{path}",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Internal-Token": self.secret,
                },
                "body": self._json.dumps(payload).encode(),
            },
            "schedule_time": ts,
        }
        self.client.create_task(request={"parent": self.parent, "task": task})
