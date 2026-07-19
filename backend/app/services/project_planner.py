"""AI project planner — the "describe your project, rent the whole kit" layer.

Given a home-project description ("I want to build a raised garden bed"),
produce a structured list of the tools the job needs. The bookings router then
matches that list against listings actually available in the neighborhood, so
the user sees a one-tap rentable kit plus any gaps.

`ClaudePlanner` calls the Anthropic API with a structured-output schema.
`FakePlanner` is a deterministic keyword matcher for dev/tests (no API key,
no network).
"""
from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, Field

from ..models import ToolCategory

PLANNER_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are the project planner inside ToolShare, a neighborhood
tool-rental app. Users describe a home/DIY project; you list the tools the job
actually needs so they can rent them from neighbors instead of buying.

Rules:
- List only physical tools someone would plausibly borrow or rent (no
  consumables like screws, lumber, paint, sandpaper — mention those in
  `consumables_note` instead).
- Prefer the common name a neighbor would list a tool under ("circular saw",
  not "7-1/4 inch sidewinder").
- Mark tools `optional: true` when the job is doable without them.
- Order by importance to the project.
- 3 to 12 tools; keep it realistic for a homeowner, not a contractor.
- Include a one-line `safety_note` when the project involves power tools,
  ladders, or electrical/plumbing work."""


class PlannedTool(BaseModel):
    name: str = Field(description="Common tool name, e.g. 'circular saw'")
    category: ToolCategory
    why: str = Field(description="One short sentence: what it's used for in this project")
    optional: bool = False


class ProjectPlan(BaseModel):
    project_summary: str = Field(description="One-line restatement of the project")
    tools: list[PlannedTool]
    consumables_note: str = Field(
        default="", description="Materials/consumables to buy rather than rent, if any"
    )
    safety_note: str = Field(default="", description="One-line safety note, if warranted")


class ProjectPlanner(Protocol):
    def plan(self, description: str) -> ProjectPlan: ...


class ClaudePlanner:
    def __init__(self, api_key: str = ""):
        import anthropic

        # Falls back to ANTHROPIC_API_KEY / ambient credentials when no key given.
        self.client = anthropic.Anthropic(api_key=api_key or None)

    def plan(self, description: str) -> ProjectPlan:
        response = self.client.messages.parse(
            model=PLANNER_MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": description}],
            output_format=ProjectPlan,
        )
        return response.parsed_output


class FakePlanner:
    """Keyword-based planner for dev and tests."""

    _RULES: list[tuple[tuple[str, ...], PlannedTool]] = [
        (
            ("garden", "bed", "plant", "yard"),
            PlannedTool(
                name="shovel", category=ToolCategory.GARDEN, why="Digging and moving soil"
            ),
        ),
        (
            ("garden", "bed", "build", "deck", "shelf", "shelves", "fence"),
            PlannedTool(
                name="circular saw",
                category=ToolCategory.POWER_TOOLS,
                why="Cutting lumber to length",
            ),
        ),
        (
            ("build", "deck", "shelf", "shelves", "fence", "hang", "mount"),
            PlannedTool(
                name="drill",
                category=ToolCategory.POWER_TOOLS,
                why="Driving screws and drilling pilot holes",
            ),
        ),
        (
            ("level", "hang", "mount", "shelf", "shelves", "fence", "deck"),
            PlannedTool(
                name="level",
                category=ToolCategory.MEASURING,
                why="Keeping the work straight and plumb",
            ),
        ),
        (
            ("paint", "wall", "ceiling"),
            PlannedTool(
                name="paint roller kit",
                category=ToolCategory.PAINTING_DECORATING,
                why="Covering large surfaces evenly",
            ),
        ),
        (
            ("gutter", "roof", "ceiling", "paint"),
            PlannedTool(
                name="ladder",
                category=ToolCategory.LADDERS_ACCESS,
                why="Reaching high work areas",
                optional=True,
            ),
        ),
    ]

    def plan(self, description: str) -> ProjectPlan:
        text = description.lower()
        tools: list[PlannedTool] = []
        for keywords, tool in self._RULES:
            if any(k in text for k in keywords) and tool.name not in [t.name for t in tools]:
                tools.append(tool)
        if not tools:
            tools = [
                PlannedTool(
                    name="drill",
                    category=ToolCategory.POWER_TOOLS,
                    why="General-purpose fastening",
                )
            ]
        return ProjectPlan(
            project_summary=description.strip()[:120],
            tools=tools,
            consumables_note="Buy fasteners and materials at the hardware store.",
            safety_note="Wear eye protection when using power tools.",
        )


def build_planner(env: str, api_key: str) -> ProjectPlanner:
    """Claude when a key is configured; keyword fake otherwise (dev/staging)."""
    if api_key:
        return ClaudePlanner(api_key)
    return FakePlanner()
