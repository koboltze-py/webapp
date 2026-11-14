"""Allgemeines Mitteilungsboard (Meldungen) - unabhängig von Krankmeldungen."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, Request, status

from ..aktivitaet import record_activity
from ..deps import get_current_role, require_schichtleitung
from ..modules_repository import get_meldungen_repository
from ..schemas import MeldungCreate, MeldungOut, MeldungUpdate

router = APIRouter(prefix="/api/meldungen", tags=["meldungen"])


def _id(row: Any) -> Any:
    return row["id"] if isinstance(row, dict) else row.id


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
    row = repo.create_meldung(payload.model_dump(), autor)
    record_activity(
        request, aktion="CREATE", bereich="Meldungen",
        entity_typ="meldung", entity_id=_id(row), entity_bezeichnung=payload.titel,
        beschreibung=f"Meldung '{payload.titel}' veröffentlicht.",
    )
    return row


@router.put("/{meldung_id}", response_model=MeldungOut)
def update_meldung(
    meldung_id: str,
    payload: MeldungUpdate,
    request: Request,
    repo=Depends(get_meldungen_repository),
    role: str = Depends(require_schichtleitung),
):
    row = repo.update_meldung(meldung_id, payload.model_dump())
    record_activity(
        request, aktion="UPDATE", bereich="Meldungen",
        entity_typ="meldung", entity_id=meldung_id, entity_bezeichnung=payload.titel,
        beschreibung=f"Meldung '{payload.titel}' bearbeitet.",
    )
    return row


@router.delete("/{meldung_id}")
def delete_meldung(
    meldung_id: str,
    request: Request,
    repo=Depends(get_meldungen_repository),
    role: str = Depends(require_schichtleitung),
):
    repo.delete_meldung(meldung_id)
    record_activity(
        request, aktion="DELETE", bereich="Meldungen",
        entity_typ="meldung", entity_id=meldung_id,
        beschreibung="Meldung gelöscht.",
    )
    return {"ok": True}
