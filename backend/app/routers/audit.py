"""Änderungsprotokoll – nur für die Rolle 'admin' einsehbar. Enthält auch
das Benutzer-Aktivitätsprotokoll (Logfile je Account, siehe aktivitaet.py):
wer wann an-/abgemeldet war und welche Aktion er ausgeführt hat."""
from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .. import supabase_client as sb
from ..aktivitaet import list_activity
from ..config import settings
from ..deps import require_admin
from ..excel_export import export_tabelle_excel
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import AuditOut, BenutzerAktivitaetOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(
    repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_admin),
):
    return repo.list_audit()


def _aktivitaet_zu_dict(a: Any) -> dict[str, Any]:
    if isinstance(a, dict):
        return a
    return {
        "id": a.id, "event_at": a.event_at, "username": a.username, "rolle": a.rolle,
        "aktion": a.aktion, "bereich": a.bereich, "entity_typ": a.entity_typ,
        "entity_id": a.entity_id, "entity_bezeichnung": a.entity_bezeichnung,
        "beschreibung": a.beschreibung, "details": a.details,
    }


def _benutzerprotokoll(username: Optional[str] = None) -> list[dict[str, Any]]:
    if settings.supabase_enabled:
        try:
            rows = sb.list_rows(
                sb.BENUTZER_AKTIVITAET_TABLE, order="event_at.desc",
                access_token=sb.get_tier_access_token("admin"),
            )
        except sb.SupabaseError:
            rows = []
    else:
        rows = [_aktivitaet_zu_dict(a) for a in list_activity()]
    if username:
        rows = [r for r in rows if (r.get("username") or "").casefold() == username.casefold()]
    return rows


@router.get("/benutzerprotokoll", response_model=List[BenutzerAktivitaetOut])
def list_benutzerprotokoll(
    username: Optional[str] = None,
    role: str = Depends(require_admin),
):
    """Logfile je Benutzerkonto (siehe models.py:BenutzerAktivitaet):
    Login/Logout + Anlegen/Bearbeiten/Löschen über alle Module hinweg.
    Optional per ?username=... auf einen Account gefiltert."""
    return _benutzerprotokoll(username)


@router.get("/benutzerprotokoll/export")
def export_benutzerprotokoll(
    username: Optional[str] = None,
    role: str = Depends(require_admin),
):
    """Excel-Export des Benutzer-Aktivitätsprotokolls, für das
    Verwaltungstool."""
    rows = _benutzerprotokoll(username)
    inhalt = export_tabelle_excel(
        titel="Benutzerprotokoll" if not username else f"Benutzerprotokoll – {username}",
        blattname="Benutzerprotokoll",
        spalten=[
            ("event_at", "Zeitpunkt"), ("username", "Benutzer"), ("rolle", "Rolle"),
            ("aktion", "Aktion"), ("bereich", "Bereich"), ("entity_bezeichnung", "Betrifft"),
            ("beschreibung", "Beschreibung"),
        ],
        zeilen=rows,
    )
    dateiname = f"Benutzerprotokoll_{date.today().isoformat()}.xlsx"
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )
