"""Benutzerverwaltung (Einzel-Logins). Ab version2.1 für Schichtleitung UND
Admin verfügbar (Schichtleitung darf laut Rollenmodell "alles außer
Careman-Status", siehe deps.py) - zuvor nur für Admin.

Kann sowohl über das Desktop-Verwaltungstool als auch direkt über die
Webapp (Einstellungen -> Benutzerverwaltung) bedient werden - beide sprechen
dieselben Endpunkte an, damit überall dieselbe Validierung/Passwort-Hashing
gilt."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, Request, status

from ..aktivitaet import record_activity
from ..deps import require_schichtleitung
from ..modules_repository import get_benutzer_repository
from ..schemas import BenutzerCreate, BenutzerOut, BenutzerUpdate
from ..security import hash_password, normalize_answer

router = APIRouter(prefix="/api/benutzer", tags=["benutzer"])


def _id(row: Any) -> Any:
    return row["id"] if isinstance(row, dict) else row.id


def _zu_out_dict(row: Any) -> dict[str, Any]:
    """BenutzerOut hat statt der Sicherheitsantwort nur ein Flag
    'hat_sicherheitsfrage' - die Antwort (auch gehasht) verlässt den Server
    nie über diesen Endpunkt."""
    d = dict(row) if isinstance(row, dict) else {
        "id": row.id, "username": row.username, "anzeigename": row.anzeigename,
        "rolle": row.rolle, "aktiv": row.aktiv, "created_at": row.created_at, "updated_at": row.updated_at,
        "sicherheitsantwort_hash": row.sicherheitsantwort_hash,
    }
    d["hat_sicherheitsfrage"] = bool(d.get("sicherheitsantwort_hash"))
    return d


@router.get("", response_model=List[BenutzerOut])
def list_benutzer(repo=Depends(get_benutzer_repository), role: str = Depends(require_schichtleitung)):
    return [_zu_out_dict(b) for b in repo.list_benutzer()]


@router.post("", response_model=BenutzerOut, status_code=status.HTTP_201_CREATED)
def create_benutzer(
    payload: BenutzerCreate,
    request: Request,
    repo=Depends(get_benutzer_repository),
    role: str = Depends(require_schichtleitung),
):
    data = payload.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    antwort = data.pop("sicherheitsantwort", "")
    data["sicherheitsantwort_hash"] = hash_password(normalize_answer(antwort)) if antwort else None
    row = repo.create_benutzer(data)
    record_activity(
        request, aktion="CREATE", bereich="Benutzerkonten",
        entity_typ="benutzer", entity_id=_id(row), entity_bezeichnung=payload.username,
        beschreibung=f"Benutzerkonto '{payload.username}' angelegt (Rolle: {payload.rolle}).",
    )
    return _zu_out_dict(row)


@router.put("/{benutzer_id}", response_model=BenutzerOut)
def update_benutzer(
    benutzer_id: str,
    payload: BenutzerUpdate,
    request: Request,
    repo=Depends(get_benutzer_repository),
    role: str = Depends(require_schichtleitung),
):
    data = payload.model_dump(exclude_unset=True)
    passwort_geaendert = False
    if "password" in data:
        password = data.pop("password")
        if password:
            data["password_hash"] = hash_password(password)
            passwort_geaendert = True
    if "sicherheitsantwort" in data:
        antwort = data.pop("sicherheitsantwort")
        if antwort:
            data["sicherheitsantwort_hash"] = hash_password(normalize_answer(antwort))
    row = repo.update_benutzer(benutzer_id, data)
    beschreibung = f"Benutzerkonto '{row['username'] if isinstance(row, dict) else row.username}' bearbeitet."
    if passwort_geaendert:
        beschreibung += " Passwort geändert."
    record_activity(
        request, aktion="UPDATE", bereich="Benutzerkonten",
        entity_typ="benutzer", entity_id=benutzer_id,
        entity_bezeichnung=row["username"] if isinstance(row, dict) else row.username,
        beschreibung=beschreibung,
    )
    return _zu_out_dict(row)
