"""Personal-Stammdaten (CRUD)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from ..deps import get_current_role, require_schichtleitung
from ..modules_repository import get_mitarbeiter_repository
from ..schemas import MitarbeiterCreate, MitarbeiterOut, MitarbeiterUpdate

router = APIRouter(prefix="/api/mitarbeiter", tags=["mitarbeiter"])


@router.get("", response_model=List[MitarbeiterOut])
def list_mitarbeiter(repo=Depends(get_mitarbeiter_repository), role: str = Depends(get_current_role)):
    return repo.list_mitarbeiter()


@router.post("", response_model=MitarbeiterOut, status_code=status.HTTP_201_CREATED)
def create_mitarbeiter(payload: MitarbeiterCreate, repo=Depends(get_mitarbeiter_repository), role: str = Depends(require_schichtleitung)):
    return repo.create_mitarbeiter(payload.model_dump())


@router.put("/{mitarbeiter_id}", response_model=MitarbeiterOut)
def update_mitarbeiter(mitarbeiter_id: str, payload: MitarbeiterUpdate, repo=Depends(get_mitarbeiter_repository), role: str = Depends(require_schichtleitung)):
    return repo.update_mitarbeiter(mitarbeiter_id, payload.model_dump())


@router.delete("/{mitarbeiter_id}")
def delete_mitarbeiter(mitarbeiter_id: str, repo=Depends(get_mitarbeiter_repository), role: str = Depends(require_schichtleitung)):
    repo.delete_mitarbeiter(mitarbeiter_id)
    return {"ok": True}
