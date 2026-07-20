"""AI build guides: step-by-step plans that reference the rented tools.

After a kit is planned/rented, the app stays open *during* the project — the
guide names each rented tool at the step where it's used, with safety notes.
Cached on the kit so regeneration is free.
"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

_PROMPT = """You are the build-guide writer inside ToolShare, a neighborhood
tool-rental app. Write a practical step-by-step guide for the user's project.

Rules:
- Aimed at a first-time DIYer; concrete, encouraging, no filler.
- 5-10 steps, each with a short title and 2-4 sentences of detail.
- In `tools`, name ONLY tools from the provided kit list that the step uses.
- Add a one-line `safety` note on steps involving power tools, ladders,
  cutting, or lifting; leave it empty otherwise.
- `est_hours` is the realistic total for a beginner, including setup.
- difficulty: easy | moderate | hard."""


class GuideStep(BaseModel):
    title: str
    detail: str
    tools: list[str] = Field(default_factory=list)
    safety: str = ""


class BuildGuide(BaseModel):
    title: str
    difficulty: str = "moderate"
    est_hours: float = 4
    steps: list[GuideStep]
    finish_note: str = ""


class GuideBuilder(Protocol):
    def build(self, description: str, tool_names: list[str]) -> BuildGuide: ...


_GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "difficulty": {"type": "STRING", "enum": ["easy", "moderate", "hard"]},
        "est_hours": {"type": "NUMBER"},
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "detail": {"type": "STRING"},
                    "tools": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "safety": {"type": "STRING"},
                },
                "required": ["title", "detail"],
            },
        },
        "finish_note": {"type": "STRING"},
    },
    "required": ["title", "steps"],
}


class GeminiGuideBuilder:
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

    def build(self, description: str, tool_names: list[str]) -> BuildGuide:
        import httpx

        user_msg = (f"Project: {description}\n"
                    f"Rented kit tools: {', '.join(tool_names) or 'none listed'}")
        resp = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self._token()}"},
            json={
                "systemInstruction": {"parts": [{"text": _PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": _GEMINI_SCHEMA,
                    "temperature": 0.4,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return BuildGuide.model_validate_json(text)


class FakeGuideBuilder:
    def build(self, description: str, tool_names: list[str]) -> BuildGuide:
        tools = tool_names[:2] or ["drill"]
        return BuildGuide(
            title=f"Weekend guide: {description[:60]}",
            difficulty="easy",
            est_hours=3,
            steps=[
                GuideStep(title="Measure and mark", detail="Lay out your dimensions "
                          "and mark all cut lines twice before cutting once.",
                          tools=tool_names[:1]),
                GuideStep(title="Cut and assemble", detail="Make your cuts, then "
                          "fasten the frame square before adding the rest.",
                          tools=tools,
                          safety="Wear eye protection while cutting."),
                GuideStep(title="Finish and clean up", detail="Sand rough edges, do a "
                          "final check, and wipe down the borrowed tools before return."),
            ],
            finish_note="Snap a photo of the finished project — neighbors love seeing "
                        "what their tools built.",
        )


def build_guide_builder(planner_backend: str, gcp_project: str,
                        gemini_model: str = "gemini-2.5-flash") -> GuideBuilder:
    if planner_backend == "gemini" and gcp_project:
        return GeminiGuideBuilder(gcp_project, model=gemini_model)
    return FakeGuideBuilder()
