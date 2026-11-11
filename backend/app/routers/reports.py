"""CRUD für Krankmeldungen. Jede Änderung wird im Änderungsprotokoll
(sick_report_audit) festgehalten. Nur die Rolle 'admin' darf den
Careman-Status setzen oder umschalten – die Disposition kann ihn weder
beim Anlegen noch beim Bearbeiten verändern (Server-seitig erzwungen,
analog zur bisherigen Supabase-Policy-Logik im Frontend).

Die eigentliche Speicherung (lokale SQLite-Datenbank oder dauerhaft in
Supabase) übernimmt die Repository-Abstraktion in ../repository.py."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from ..deps import get_current_role, require_admin
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import CaremanUpdate, ReportCreate, ReportOut, ReportUpdate

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=List[ReportOut])
def list_reports(
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    return repo.list_reports()


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    return repo.create_report(payload.model_dump(), role)


@router.put("/{report_id}", response_model=ReportOut)
def update_report(
    report_id: str,
    payload: ReportUpdate,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    return repo.update_report(report_id, payload.model_dump(), role)


@router.patch("/{report_id}/careman", response_model=ReportOut)
def toggle_careman(
    report_id: str,
    payload: CaremanUpdate,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_admin),
):
    return repo.toggle_careman(report_id, payload.careman_done, role)


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    repo.delete_report(report_id, role)
    return {"ok": True}
