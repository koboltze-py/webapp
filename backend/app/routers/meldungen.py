"""Allgemeines Mitteilungsboard (Meldungen) - unabhängig von Krankmeldungen."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request, status

from ..deps import get_current_role, require_schichtleitung
from ..modules_repository import get_meldungen_repository
from ..schemas import MeldungCreate, MeldungOut, MeldungUpdate

router = APIRouter(prefix="/api/meldungen", tags=["meldungen"])


@router.get("", response_model=List[MeldungOut])
def list_meldungen(repo=Depends(get_meldungen_repository), role: str = Depends(get_current_role)):
    return repo.list_meldungen()


@router.post("", response_model=MeldungOut, status_code=status.HTTP_201_CREATED)
def create_meldung(
    payload: MeldungCreate,
    request: Request,
    repo=Depends(get_meldungen_repository),
    role: str = Depends(require_schichtleitung),
):
    autor = request.session.get("username", role)
    return repo.create_meldung(payload.model_dump(), autor)


@router.put("/{meldung_id}", response_model=MeldungOut)
def update_meldung(meldung_id: str, payload: MeldungUpdate, repo=Depends(get_meldungen_repository), role: str = Depends(require_schichtleitung)):
    return repo.update_meldung(meldung_id, payload.model_dump())


@router.delete("/{meldung_id}")
def delete_meldung(meldung_id: str, repo=Depends(get_meldungen_repository), role: str = Depends(require_schichtleitung)):
    repo.delete_meldung(meldung_id)
    return {"ok": True}
