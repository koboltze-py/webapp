"""Hilfsfunktionen zum Schreiben von Änderungsprotokoll-Einträgen."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import AuditLog, SickReport


def snapshot(report: SickReport) -> dict:
    """Erzeugt ein JSON-serialisierbares Abbild einer Krankmeldung für das
    Änderungsprotokoll (vorher/nachher-Vergleich im Frontend)."""
    return {
        "reported_at": report.reported_at.isoformat() if report.reported_at else None,
        "employee": report.employee,
        "sick_from": report.sick_from.isoformat() if report.sick_from else None,
        "sick_to": report.sick_to.isoformat() if report.sick_to else None,
        "call_at": report.call_at.isoformat(timespec="minutes") if report.call_at else None,
        "accepted_by": report.accepted_by,
        "notes": report.notes,
        "careman_done": report.careman_done,
    }


def write_audit(
    db: Session,
    *,
    action: str,
    report_id: Optional[int],
    old_data: Optional[dict],
    new_data: Optional[dict],
    actor_role: str,
) -> None:
    entry = AuditLog(
        event_at=datetime.utcnow(),
        report_id=report_id,
        action=action,
        actor_role=actor_role,
        old_data=old_data,
        new_data=new_data,
    )
    db.add(entry)
    db.commit()
