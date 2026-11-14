"""Dienstplan: Anzeige + Excel-Import (siehe app/dienstplan_parser.py) +
Sortierung/Kategorisierung (siehe app/dienstplan_sortierung.py) + manuelle
Korrekturen mit Änderungsprotokoll."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from ..deps import get_current_role, require_admin, require_schichtleitung
from ..dienstplan_parser import parse_dienstplan_excel
from ..dienstplan_sortierung import kategorisiere_und_sortiere
from ..modules_repository import get_dienstplan_repository
from ..schemas import (
    DienstplanAuditOut,
    DienstplanEintragOut,
    DienstplanEintragUpdate,
    DienstplanImportResult,
    DienstplanQuelle,
)

router = APIRouter(prefix="/api/dienstplan", tags=["dienstplan"])


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id, "datum": row.datum, "mitarbeiter_name": row.mitarbeiter_name,
        "dienst_kategorie": row.dienst_kategorie, "start_zeit": row.start_zeit, "end_zeit": row.end_zeit,
        "ist_krank": row.ist_krank, "ist_bulmorfahrer": row.ist_bulmorfahrer, "notiz": row.notiz,
        "quelle_datei": row.quelle_datei, "created_at": row.created_at,
    }


@router.get("", response_model=List[DienstplanEintragOut])
def list_dienstplan(
    von: Optional[date] = None,
    bis: Optional[date] = None,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    rows = [_row_to_dict(r) for r in repo.list_eintraege(von, bis)]
    return kategorisiere_und_sortiere(rows)


@router.get("/quelle", response_model=DienstplanQuelle)
def get_quelle(
    datum: date,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    """Woher die angezeigten Daten stammen (Excel-Dateiname + Importzeitpunkt),
    damit sichtbar ist, dass von der importierten Datenbank gearbeitet wird."""
    return repo.get_quelle(datum)


@router.get("/audit", response_model=List[DienstplanAuditOut])
def list_dienstplan_audit(
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(require_admin),
):
    return repo.list_audit()


@router.put("/{eintrag_id}", response_model=DienstplanEintragOut)
def update_dienstplan_eintrag(
    eintrag_id: str,
    payload: DienstplanEintragUpdate,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(require_schichtleitung),
):
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Änderungen übermittelt.")
    actor_username = request.session.get("username", role)
    row = repo.update_eintrag(eintrag_id, data, role, actor_username)
    return kategorisiere_und_sortiere([_row_to_dict(row)])[0]


@router.post("/import", response_model=DienstplanImportResult)
async def import_dienstplan(
    datei: UploadFile,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(require_schichtleitung),
):
    if not datei.filename or not datei.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bitte eine Excel-Datei (.xlsx) hochladen.")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await datei.read())
        tmp_path = Path(tmp.name)

    try:
        ergebnis = parse_dienstplan_excel(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not ergebnis["success"]:
        return DienstplanImportResult(success=False, error=ergebnis["error"])

    tag = ergebnis["datum"] or date.today()
    eintraege = [
        {
            "mitarbeiter_name": e["mitarbeiter_name"],
            "dienst_kategorie": e["dienst_kategorie"],
            "start_zeit": e["start_zeit"],
            "end_zeit": e["end_zeit"],
            "ist_krank": e["ist_krank"],
            "ist_bulmorfahrer": e["ist_bulmorfahrer"],
            "notiz": e["notiz"],
        }
        for e in ergebnis["eintraege"]
    ]
    repo.replace_tag(tag, eintraege, datei.filename)

    return DienstplanImportResult(
        success=True,
        datum=tag,
        anzahl_eintraege=len(eintraege),
        anzahl_krank=sum(1 for e in eintraege if e["ist_krank"]),
        anzahl_bulmorfahrer=sum(1 for e in eintraege if e["ist_bulmorfahrer"]),
        unbekannte_dienste=ergebnis["unbekannte_dienste"],
    )

