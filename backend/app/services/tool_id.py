"""Photo-to-listing: identify a tool from one photo and draft the listing.

The single biggest supply-side friction is the listing form. This turns it
into: snap a photo -> Gemini names the tool, writes the description, and
suggests a fair daily price and deposit -> owner taps confirm.

Backends mirror the project planner: Vertex AI Gemini (vision) via the
service's own GCP identity in prod, a deterministic fake in dev/tests.
"""
from __future__ import annotations

import base64
from typing import Protocol

from pydantic import BaseModel, Field

from ..models import ToolCategory

_PROMPT = """You are the listing assistant inside ToolShare, a neighborhood
tool-rental app. Identify the tool in the photo and draft its rental listing.

Rules:
- title: brand + common tool name if the brand is visible ("DeWalt 20V
  cordless drill"), else just the common name a neighbor would search for.
- description: 1-2 sentences a renter cares about (what it does, notable
  accessories visible in the photo). Never invent accessories you can't see.
- price_per_day_cents: a fair neighborhood daily rate in cents, typically
  500-1500 for hand/garden tools, 700-2000 for power tools, more for
  specialty gear. Minimum 500.
- deposit_cents: roughly 30-60% of the tool's replacement cost, rounded to
  the nearest $5. 0 for cheap hand tools.
- confidence 0-1: how sure you are this identification is right.
- If the photo clearly isn't a tool, set confidence below 0.3 and take your
  best guess at what a tool-lending neighbor might have meant."""


class ToolIdSuggestion(BaseModel):
    title: str = Field(max_length=120)
    category: ToolCategory = ToolCategory.OTHER
    description: str = Field(default="", max_length=500)
    condition: str = "good"
    price_per_day_cents: int = Field(default=800, ge=500, le=50_000)
    deposit_cents: int = Field(default=0, ge=0, le=200_000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class ToolIdentifier(Protocol):
    def identify(self, image: bytes, content_type: str) -> ToolIdSuggestion: ...


_GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "category": {"type": "STRING", "enum": [c.value for c in ToolCategory]},
        "description": {"type": "STRING"},
        "condition": {"type": "STRING", "enum": ["like new", "good", "worn"]},
        "price_per_day_cents": {"type": "INTEGER"},
        "deposit_cents": {"type": "INTEGER"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["title", "category", "price_per_day_cents", "confidence"],
}


class GeminiToolIdentifier:
    """Vertex AI Gemini vision via REST with ADC — no API key needed on GCP."""

    def __init__(self, project: str, region: str = "us-central1",
                 model: str = "gemini-2.5-flash"):
        import google.auth

        self._creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.url = (
            f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{region}/publishers/google/models/{model}:generateContent"
        )

    def _token(self) -> str:
        import google.auth.transport.requests

        if not self._creds.valid:
            self._creds.refresh(google.auth.transport.requests.Request())
        return self._creds.token

    def identify(self, image: bytes, content_type: str) -> ToolIdSuggestion:
        import httpx

        resp = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self._token()}"},
            json={
                "systemInstruction": {"parts": [{"text": _PROMPT}]},
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"inlineData": {
                            "mimeType": content_type or "image/jpeg",
                            "data": base64.b64encode(image).decode(),
                        }},
                        {"text": "Identify this tool and draft its listing."},
                    ],
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": _GEMINI_SCHEMA,
                    "temperature": 0.2,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        s = ToolIdSuggestion.model_validate_json(text)
        # Clamp to marketplace price rules regardless of what the model says.
        s.price_per_day_cents = max(500, min(s.price_per_day_cents, 50_000))
        s.deposit_cents = max(0, min(s.deposit_cents, 200_000))
        return s


class FakeToolIdentifier:
    """Deterministic suggestion for dev and tests (no network)."""

    def identify(self, image: bytes, content_type: str) -> ToolIdSuggestion:
        return ToolIdSuggestion(
            title="Cordless drill",
            category=ToolCategory.POWER_TOOLS,
            description="Compact cordless drill/driver — good for furniture, "
                        "shelves and general fastening.",
            condition="good",
            price_per_day_cents=700,
            deposit_cents=4000,
            confidence=0.92,
        )


def build_identifier(planner_backend: str, gcp_project: str,
                     gemini_model: str = "gemini-2.5-flash") -> ToolIdentifier:
    if planner_backend == "gemini" and gcp_project:
        return GeminiToolIdentifier(gcp_project, model=gemini_model)
    return FakeToolIdentifier()
