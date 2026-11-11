"""Änderungsprotokoll – nur für die Rolle 'admin' einsehbar."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ..deps import require_admin
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import AuditOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_admin),
):
    return repo.list_audit()
