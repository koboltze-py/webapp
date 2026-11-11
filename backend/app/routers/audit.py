"""Änderungsprotokoll – nur für die Rolle 'admin' einsehbar."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog
from ..schemas import AuditOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(db: Session = Depends(get_db), role: str = Depends(require_admin)):
    return (
        db.query(AuditLog)
        .order_by(AuditLog.event_at.desc(), AuditLog.id.desc())
        .all()
    )
