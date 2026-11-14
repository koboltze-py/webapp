"""Benutzerverwaltung (Einzel-Logins). Nur für Admin.

Das vorgesehene Desktop-GUI-Tool zum Anlegen neuer Logins (siehe
Projektplan) spricht diese Endpunkte an, statt die Datenbank direkt zu
beschreiben - so gilt überall dieselbe Validierung/Passwort-Hashing."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from ..deps import require_admin
from ..modules_repository import get_benutzer_repository
from ..schemas import BenutzerCreate, BenutzerOut, BenutzerUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/benutzer", tags=["benutzer"])


@router.get("", response_model=List[BenutzerOut])
def list_benutzer(repo=Depends(get_benutzer_repository), role: str = Depends(require_admin)):
    return repo.list_benutzer()


@router.post("", response_model=BenutzerOut, status_code=status.HTTP_201_CREATED)
def create_benutzer(payload: BenutzerCreate, repo=Depends(get_benutzer_repository), role: str = Depends(require_admin)):
    data = payload.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    return repo.create_benutzer(data)


@router.put("/{benutzer_id}", response_model=BenutzerOut)
def update_benutzer(benutzer_id: str, payload: BenutzerUpdate, repo=Depends(get_benutzer_repository), role: str = Depends(require_admin)):
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            data["password_hash"] = hash_password(password)
    return repo.update_benutzer(benutzer_id, data)
