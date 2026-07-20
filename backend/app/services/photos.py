"""Photo storage: GCS in production (public bucket), in-memory in dev.

Both return a URL the browser can render directly. Memory-store photos are
served by GET /v1/photos/{name}.
"""
from __future__ import annotations

import uuid
from typing import Optional, Protocol

_EXT = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/svg+xml": "svg", "image/gif": "gif",
}

MAX_PHOTO_BYTES = 5 * 1024 * 1024


class PhotoStore(Protocol):
    def save(self, data: bytes, content_type: str) -> str: ...
    def get(self, name: str) -> Optional[tuple[bytes, str]]: ...
    def load(self, url: str) -> Optional[tuple[bytes, str]]: ...


def make_name(content_type: str) -> str:
    return f"{uuid.uuid4().hex}.{_EXT.get(content_type, 'jpg')}"


class MemoryPhotoStore:
    def __init__(self):
        self.blobs: dict[str, tuple[bytes, str]] = {}

    def save(self, data: bytes, content_type: str) -> str:
        name = make_name(content_type)
        self.blobs[name] = (data, content_type)
        return f"/v1/photos/{name}"

    def get(self, name: str) -> Optional[tuple[bytes, str]]:
        return self.blobs.get(name)

    def load(self, url: str) -> Optional[tuple[bytes, str]]:
        return self.get(url.rsplit("/", 1)[-1])


class GcsPhotoStore:
    def __init__(self, bucket_name: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket_name)
        self.bucket_name = bucket_name

    def save(self, data: bytes, content_type: str) -> str:
        name = make_name(content_type)
        blob = self.bucket.blob(f"photos/{name}")
        blob.upload_from_string(data, content_type=content_type)
        return f"https://storage.googleapis.com/{self.bucket_name}/photos/{name}"

    def get(self, name: str) -> Optional[tuple[bytes, str]]:
        return None  # GCS photos are served directly by the public bucket

    def load(self, url: str) -> Optional[tuple[bytes, str]]:
        """Fetch photo bytes back for AI analysis (damage comparison)."""
        prefix = f"https://storage.googleapis.com/{self.bucket_name}/"
        if not url.startswith(prefix):
            return None
        blob = self.bucket.blob(url.removeprefix(prefix))
        try:
            data = blob.download_as_bytes()
        except Exception:
            return None
        return data, blob.content_type or "image/jpeg"
