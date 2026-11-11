"""CRUD für Krankmeldungen. Jede Änderung wird im Änderungsprotokoll
(sick_report_audit) festgehalten. Nur die Rolle 'admin' darf den
Careman-Status setzen oder umschalten – die Disposition kann ihn weder
beim Anlegen noch beim Bearbeiten verändern (Server-seitig erzwungen,
analog zur bisherigen Supabase-Policy-Logik im Frontend)."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import snapshot, write_audit
from ..database import get_db
from ..deps import get_current_role, require_admin
from ..models import SickReport
from ..schemas import CaremanUpdate, ReportCreate, ReportOut, ReportUpdate

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _validate_dates(sick_from, sick_to) -> None:
    if sick_to < sick_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="„Krank bis“ darf nicht vor „Krank von“ liegen.",
        )


@router.get("", response_model=List[ReportOut])
def list_reports(db: Session = Depends(get_db), role: str = Depends(get_current_role)):
    return (
        db.query(SickReport)
        .order_by(SickReport.reported_at.desc(), SickReport.created_at.desc())
        .all()
    )


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    role: str = Depends(get_current_role),
):
    _validate_dates(payload.sick_from, payload.sick_to)
    data = payload.model_dump()
    if role != "admin":
        data["careman_done"] = False  # Careman wird von der Disposition niemals mitgeschickt

    report = SickReport(**data)
    db.add(report)
    db.commit()
    db.refresh(report)

    write_audit(
        db,
        action="INSERT",
        report_id=report.id,
        old_data=None,
        new_data=snapshot(report),
        actor_role=role,
    )
    return report


@router.put("/{report_id}", response_model=ReportOut)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
    role: str = Depends(get_current_role),
):
    report = db.get(SickReport, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

    _validate_dates(payload.sick_from, payload.sick_to)
    old_data = snapshot(report)

    data = payload.model_dump()
    if role != "admin":
        data["careman_done"] = report.careman_done  # Disposition darf Careman nicht ändern

    for key, value in data.items():
        setattr(report, key, value)
    report.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(report)

    write_audit(
        db,
        action="UPDATE",
        report_id=report.id,
        old_data=old_data,
        new_data=snapshot(report),
        actor_role=role,
    )
    return report


@router.patch("/{report_id}/careman", response_model=ReportOut)
def toggle_careman(
    report_id: int,
    payload: CaremanUpdate,
    db: Session = Depends(get_db),
    role: str = Depends(require_admin),
):
    report = db.get(SickReport, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

    old_data = snapshot(report)
    report.careman_done = payload.careman_done
    report.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(report)

    write_audit(
        db,
        action="UPDATE",
        report_id=report.id,
        old_data=old_data,
        new_data=snapshot(report),
        actor_role=role,
    )
    return report


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_current_role),
):
    report = db.get(SickReport, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

    old_data = snapshot(report)
    db.delete(report)
    db.commit()

    write_audit(
        db,
        action="DELETE",
        report_id=report_id,
        old_data=old_data,
        new_data=None,
        actor_role=role,
    )
    return {"ok": True}
