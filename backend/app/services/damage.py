"""AI condition check: compare handoff and return photos of a tool.

Makes ToolShare Guarantee claims adjudicable in minutes instead of he-said
she-said: the lender runs the check before confirming a return; the verdict
and notes are stored on the booking's audit trail.
"""
from __future__ import annotations

import base64
from typing import Protocol

from pydantic import BaseModel, Field

_PROMPT = """You are the condition checker inside ToolShare, a neighborhood
tool-rental app. You get two photos of the same rented tool: BEFORE (at
pickup) and AFTER (at return). Compare them.

Rules:
- verdict "ok": no new visible damage beyond normal use.
- verdict "damage_suspected": clearly new cracks, breaks, missing parts,
  bent components, or heavy new wear visible in AFTER but not BEFORE.
- verdict "inconclusive": photos too different in angle/lighting/quality to
  judge, or they don't appear to show the same tool.
- notes: 1-2 concrete sentences describing exactly what you compared and saw.
  Never invent damage; when unsure, prefer "inconclusive"."""


class DamageResult(BaseModel):
    verdict: str = Field(pattern="^(ok|damage_suspected|inconclusive)$")
    notes: str = ""


class DamageChecker(Protocol):
    def compare(self, before: bytes, before_type: str,
                after: bytes, after_type: str) -> DamageResult: ...


_GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING", "enum": ["ok", "damage_suspected", "inconclusive"]},
        "notes": {"type": "STRING"},
    },
    "required": ["verdict", "notes"],
}


class GeminiDamageChecker:
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

    def compare(self, before: bytes, before_type: str,
                after: bytes, after_type: str) -> DamageResult:
        import httpx

        resp = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self._token()}"},
            json={
                "systemInstruction": {"parts": [{"text": _PROMPT}]},
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": "BEFORE (pickup):"},
                        {"inlineData": {"mimeType": before_type or "image/jpeg",
                                        "data": base64.b64encode(before).decode()}},
                        {"text": "AFTER (return):"},
                        {"inlineData": {"mimeType": after_type or "image/jpeg",
                                        "data": base64.b64encode(after).decode()}},
                        {"text": "Compare and report."},
                    ],
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": _GEMINI_SCHEMA,
                    "temperature": 0.1,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return DamageResult.model_validate_json(text)


class FakeDamageChecker:
    def compare(self, before: bytes, before_type: str,
                after: bytes, after_type: str) -> DamageResult:
        # Deterministic for tests: identical bytes = ok, different = suspected.
        if before == after:
            return DamageResult(verdict="ok",
                                notes="Return photo matches the pickup photo — no new damage visible.")
        return DamageResult(verdict="damage_suspected",
                            notes="The return photo differs from pickup — review before releasing the deposit.")


def build_damage_checker(planner_backend: str, gcp_project: str,
                         gemini_model: str = "gemini-2.5-flash") -> DamageChecker:
    if planner_backend == "gemini" and gcp_project:
        return GeminiDamageChecker(gcp_project, model=gemini_model)
    return FakeDamageChecker()
