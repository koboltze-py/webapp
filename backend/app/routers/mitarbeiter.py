"""Personal-Stammdaten (CRUD) + Mitarbeiter-Historie (siehe
mitarbeiter_historie.py: wie oft/wann jemand krank war, Stammdaten-
Änderungen) und Benutzer-Aktivitätsprotokoll (siehe aktivitaet.py)."""
from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from .. import supabase_client as sb
from ..aktivitaet import record_activity
from ..config import settings
from ..deps import get_current_role, require_admin, require_schichtleitung
from ..excel_export import export_tabelle_excel
from ..mitarbeiter_historie import list_alle_ereignisse, list_ereignisse, record_ereignis
from ..modules_repository import get_mitarbeiter_repository
from ..schemas import MitarbeiterCreate, MitarbeiterHistorieOut, MitarbeiterOut, MitarbeiterUpdate

router = APIRouter(prefix="/api/mitarbeiter", tags=["mitarbeiter"])


def _name(payload_or_row: Any) -> str:
    vorname = payload_or_row["vorname"] if isinstance(payload_or_row, dict) else payload_or_row.vorname
    nachname = payload_or_row["nachname"] if isinstance(payload_or_row, dict) else payload_or_row.nachname
    return f"{vorname} {nachname}".strip()


def _id(row: Any) -> Any:
    return row["id"] if isinstance(row, dict) else row.id


@router.get("", response_model=List[MitarbeiterOut])
def list_mitarbeiter(repo=Depends(get_mitarbeiter_repository), role: str = Depends(get_current_role)):
    return repo.list_mitarbeiter()


@router.post("", response_model=MitarbeiterOut, status_code=status.HTTP_201_CREATED)
def create_mitarbeiter(
    payload: MitarbeiterCreate,
    request: Request,
    repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_schichtleitung),
):
    actor_username = request.session.get("username", role)
    row = repo.create_mitarbeiter(payload.model_dump())
    record_ereignis(
        mitarbeiter_id=_id(row), mitarbeiter_name=_name(row), ereignis_typ="stammdaten_angelegt",
        beschreibung="Mitarbeiter:in angelegt.", bezug_typ="mitarbeiter", bezug_id=_id(row),
        actor_username=actor_username, actor_role=role,
    )
    record_activity(
        request, aktion="CREATE", bereich="Mitarbeiter-Stammdaten",
        entity_typ="mitarbeiter", entity_id=_id(row), entity_bezeichnung=_name(row),
        beschreibung=f"Mitarbeiter:in '{_name(row)}' angelegt.",
    )
    return row


@router.put("/{mitarbeiter_id}", response_model=MitarbeiterOut)
def update_mitarbeiter(
    mitarbeiter_id: str,
    payload: MitarbeiterUpdate,
    request: Request,
    repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_schichtleitung),
):
    actor_username = request.session.get("username", role)
    row = repo.update_mitarbeiter(mitarbeiter_id, payload.model_dump())
    ereignis_typ = "stammdaten_deaktiviert" if not payload.aktiv else "stammdaten_geaendert"
    record_ereignis(
        mitarbeiter_id=_id(row), mitarbeiter_name=_name(row), ereignis_typ=ereignis_typ,
        beschreibung="Stammdaten bearbeitet." if payload.aktiv else "Auf 'Inaktiv' gesetzt.",
        bezug_typ="mitarbeiter", bezug_id=_id(row), actor_username=actor_username, actor_role=role,
    )
    record_activity(
        request, aktion="UPDATE", bereich="Mitarbeiter-Stammdaten",
        entity_typ="mitarbeiter", entity_id=mitarbeiter_id, entity_bezeichnung=_name(row),
        beschreibung=f"Mitarbeiter:in '{_name(row)}' bearbeitet.",
    )
    return row


@router.delete("/{mitarbeiter_id}")
def delete_mitarbeiter(
    mitarbeiter_id: str,
    request: Request,
    repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_schichtleitung),
):
    bestehende = {str(_id(m)): m for m in repo.list_mitarbeiter()}
    name = _name(bestehende[mitarbeiter_id]) if mitarbeiter_id in bestehende else ""
    actor_username = request.session.get("username", role)
    repo.delete_mitarbeiter(mitarbeiter_id)
    record_ereignis(
        mitarbeiter_id=None, mitarbeiter_name=name, ereignis_typ="stammdaten_geloescht",
        beschreibung="Stammdatensatz gelöscht.", bezug_typ="mitarbeiter", bezug_id=mitarbeiter_id,
        actor_username=actor_username, actor_role=role,
    )
    record_activity(
        request, aktion="DELETE", bereich="Mitarbeiter-Stammdaten",
        entity_typ="mitarbeiter", entity_id=mitarbeiter_id, entity_bezeichnung=name,
        beschreibung=f"Mitarbeiter:in '{name}' gelöscht.",
    )
    return {"ok": True}


def _ereignis_zu_dict(e: Any) -> dict[str, Any]:
    if isinstance(e, dict):
        return e
    return {
        "id": e.id, "event_at": e.event_at, "mitarbeiter_id": e.mitarbeiter_id,
        "mitarbeiter_name": e.mitarbeiter_name, "ereignis_typ": e.ereignis_typ,
        "beschreibung": e.beschreibung, "bezug_typ": e.bezug_typ, "bezug_id": e.bezug_id,
        "actor_username": e.actor_username, "actor_role": e.actor_role, "details": e.details,
    }


EREIGNIS_LABEL = {
    "krank_gemeldet": "Krank gemeldet",
    "krankmeldung_aktualisiert": "Krankmeldung aktualisiert",
    "krankmeldung_geloescht": "Krankmeldung gelöscht",
    "dienstplan_krank_aufgehoben": "Krank-Status im Dienstplan aufgehoben",
    "stammdaten_angelegt": "Stammdaten angelegt",
    "stammdaten_geaendert": "Stammdaten geändert",
    "stammdaten_deaktiviert": "Stammdaten deaktiviert",
    "stammdaten_geloescht": "Stammdaten gelöscht",
}


@router.get("/historie/export")
def export_mitarbeiter_historie(
    mitarbeiter_id: Optional[str] = None,
    role: str = Depends(require_admin),
):
    """Excel-Export der Mitarbeiter-Historie (siehe mitarbeiter_historie.py) -
    standardmäßig über ALLE Mitarbeitenden, optional auf eine Person
    gefiltert (?mitarbeiter_id=...). Für das Verwaltungstool."""
    if settings.supabase_enabled:
        try:
            rows = sb.list_rows(
                sb.MITARBEITER_EREIGNIS_TABLE, order="event_at.desc",
                access_token=sb.get_tier_access_token("admin"),
            )
        except sb.SupabaseError:
            rows = []
    else:
        rows = [_ereignis_zu_dict(e) for e in list_alle_ereignisse()]

    if mitarbeiter_id:
        rows = [r for r in rows if str(r.get("mitarbeiter_id")) == str(mitarbeiter_id)]

    for r in rows:
        r["ereignis_label"] = EREIGNIS_LABEL.get(r["ereignis_typ"], r["ereignis_typ"])

    inhalt = export_tabelle_excel(
        titel="Mitarbeiter-Historie" if not mitarbeiter_id else f"Mitarbeiter-Historie (ID {mitarbeiter_id})",
        blattname="Mitarbeiter-Historie",
        spalten=[
            ("event_at", "Zeitpunkt"), ("mitarbeiter_name", "Mitarbeiter:in"),
            ("ereignis_label", "Ereignis"), ("beschreibung", "Beschreibung"),
            ("bezug_typ", "Bezug"), ("actor_username", "Durchgeführt von"), ("actor_role", "Rolle"),
        ],
        zeilen=rows,
    )
    dateiname = f"Mitarbeiter-Historie_{date.today().isoformat()}.xlsx"
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@router.get("/{mitarbeiter_id}/historie", response_model=MitarbeiterHistorieOut)
def get_mitarbeiter_historie(
    mitarbeiter_id: str,
    role: str = Depends(require_schichtleitung),
):
    """Historie + verdichtete Kennzahlen (wie oft/wann krank gemeldet,
    Stammdaten-Änderungen) eines einzelnen Mitarbeiters, siehe
    mitarbeiter_historie.py und models.py:MitarbeiterEreignis."""
    if settings.supabase_enabled:
        try:
            alle = sb.list_rows(
                sb.MITARBEITER_EREIGNIS_TABLE, order="event_at.desc",
                access_token=sb.get_tier_access_token("admin"),
            )
        except sb.SupabaseError:
            alle = []
        rows = [r for r in alle if str(r.get("mitarbeiter_id")) == str(mitarbeiter_id)]
    else:
        try:
            mid = int(mitarbeiter_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        rows = [_ereignis_zu_dict(e) for e in list_ereignisse(mid)]

    krank_ereignisse = [r for r in rows if r["ereignis_typ"] == "krank_gemeldet"]
    tage_gesamt = 0
    for r in krank_ereignisse:
        details = r.get("details") or {}
        von, bis = details.get("sick_from"), details.get("sick_to")
        if von and bis:
            try:
                d_von, d_bis = date.fromisoformat(von), date.fromisoformat(bis)
                tage_gesamt += max((d_bis - d_von).days + 1, 0)
            except ValueError:
                pass
    letzte = krank_ereignisse[0]["details"] if krank_ereignisse else None

    return MitarbeiterHistorieOut(
        mitarbeiter_id=mitarbeiter_id,
        anzahl_krankmeldungen=len(krank_ereignisse),
        anzahl_krank_tage_gesamt=tage_gesamt,
        letzte_krankmeldung_von=(letzte or {}).get("sick_from") if letzte else None,
        letzte_krankmeldung_bis=(letzte or {}).get("sick_to") if letzte else None,
        ereignisse=rows,
    )
