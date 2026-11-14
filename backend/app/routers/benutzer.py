"""Benutzerverwaltung (Einzel-Logins). Nur für Admin.

Das vorgesehene Desktop-GUI-Tool zum Anlegen neuer Logins (siehe
Projektplan) spricht diese Endpunkte an, statt die Datenbank direkt zu
beschreiben - so gilt überall dieselbe Validierung/Passwort-Hashing."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, Request, status

from ..aktivitaet import record_activity
from ..deps import require_admin
from ..modules_repository import get_benutzer_repository
from ..schemas import BenutzerCreate, BenutzerOut, BenutzerUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/benutzer", tags=["benutzer"])


def _id(row: Any) -> Any:
    return row["id"] if isinstance(row, dict) else row.id


@router.get("", response_model=List[BenutzerOut])
def list_benutzer(repo=Depends(get_benutzer_repository), role: str = Depends(require_admin)):
    return repo.list_benutzer()


@router.post("", response_model=BenutzerOut, status_code=status.HTTP_201_CREATED)
def create_benutzer(
    payload: BenutzerCreate,
    request: Request,
    repo=Depends(get_benutzer_repository),
    role: str = Depends(require_admin),
):
    data = payload.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    row = repo.create_benutzer(data)
    record_activity(
        request, aktion="CREATE", bereich="Benutzerkonten",
        entity_typ="benutzer", entity_id=_id(row), entity_bezeichnung=payload.username,
        beschreibung=f"Benutzerkonto '{payload.username}' angelegt (Rolle: {payload.rolle}).",
    )
    return row


@router.put("/{benutzer_id}", response_model=BenutzerOut)
def update_benutzer(
    benutzer_id: str,
    payload: BenutzerUpdate,
    request: Request,
    repo=Depends(get_benutzer_repository),
    role: str = Depends(require_admin),
):
    data = payload.model_dump(exclude_unset=True)
    passwort_geaendert = False
    if "password" in data:
        password = data.pop("password")
        if password:
            data["password_hash"] = hash_password(password)
            passwort_geaendert = True
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
    return row
