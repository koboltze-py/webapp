"""CRUD für Krankmeldungen. Jede Änderung wird im Änderungsprotokoll
(sick_report_audit) UND in der Mitarbeiter-Historie (siehe
mitarbeiter_historie.py) festgehalten. Nur die Rolle 'admin' darf den
Careman-Status setzen oder umschalten – die Disposition kann ihn weder
beim Anlegen noch beim Bearbeiten verändern (Server-seitig erzwungen,
analog zur bisherigen Supabase-Policy-Logik im Frontend).

Die eigentliche Speicherung (lokale SQLite-Datenbank oder dauerhaft in
Supabase) übernimmt die Repository-Abstraktion in ../repository.py."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request, status

from ..aktivitaet import record_activity
from ..deps import get_current_role, require_admin, require_schichtleitung
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import CaremanUpdate, ReportCreate, ReportOut, ReportUpdate

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _entity_id(obj) -> object:
    """ID eines Repository-Ergebnisses, egal ob ORM-Objekt (lokal) oder
    dict (Supabase-Zeile)."""
    return obj["id"] if isinstance(obj, dict) else obj.id


@router.get("", response_model=List[ReportOut])
def list_reports(
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_schichtleitung),
):
    return repo.list_reports()


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    request: Request,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_schichtleitung),
):
    actor_username = request.session.get("username", role)
    report = repo.create_report(payload.model_dump(), role, actor_username)
    record_activity(
        request, aktion="CREATE", bereich="Krankmeldungen",
        entity_typ="sick_report", entity_id=_entity_id(report),
        entity_bezeichnung=payload.employee,
        beschreibung=f"Krankmeldung angelegt: {payload.employee} ({payload.sick_from} bis {payload.sick_to})",
    )
    return report


@router.put("/{report_id}", response_model=ReportOut)
def update_report(
    report_id: str,
    payload: ReportUpdate,
    request: Request,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_schichtleitung),
):
    actor_username = request.session.get("username", role)
    report = repo.update_report(report_id, payload.model_dump(), role, actor_username)
    record_activity(
        request, aktion="UPDATE", bereich="Krankmeldungen",
        entity_typ="sick_report", entity_id=report_id, entity_bezeichnung=payload.employee,
        beschreibung=f"Krankmeldung bearbeitet: {payload.employee}",
    )
    return report


@router.patch("/{report_id}/careman", response_model=ReportOut)
def toggle_careman(
    report_id: str,
    payload: CaremanUpdate,
    request: Request,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_admin),
):
    report = repo.toggle_careman(report_id, payload.careman_done, role)
    record_activity(
        request, aktion="UPDATE", bereich="Krankmeldungen",
        entity_typ="sick_report", entity_id=report_id,
        beschreibung=f"Careman-Status gesetzt auf {'erledigt' if payload.careman_done else 'offen'}",
    )
    return report


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    request: Request,
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_schichtleitung),
):
    actor_username = request.session.get("username", role)
    repo.delete_report(report_id, role, actor_username)
    record_activity(
        request, aktion="DELETE", bereich="Krankmeldungen",
        entity_typ="sick_report", entity_id=report_id,
        beschreibung="Krankmeldung gelöscht.",
    )
    return {"ok": True}
