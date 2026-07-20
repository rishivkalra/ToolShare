"""Trust & safety: report a listing, user, or booking for review."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import current_uid
from ..deps import Container, get_container
from ..models import Report, ReportCreate
from ..repos.memory import next_id

router = APIRouter(prefix="/v1/reports", tags=["safety"])


@router.post("", response_model=Report, status_code=201)
def create_report(
    body: ReportCreate,
    uid: str = Depends(current_uid),
    c: Container = Depends(get_container),
):
    report = Report(
        id=next_id("rpt"),
        reporter_uid=uid,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        created_at=datetime.now(timezone.utc),
    )
    return c.reports.create(report)
