"""Dienstplan: Anzeige + Excel-Import (siehe app/dienstplan_parser.py)."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from ..deps import get_current_role, require_schichtleitung
from ..dienstplan_parser import parse_dienstplan_excel
from ..modules_repository import get_dienstplan_repository
from ..schemas import DienstplanEintragOut, DienstplanImportResult

router = APIRouter(prefix="/api/dienstplan", tags=["dienstplan"])


@router.get("", response_model=List[DienstplanEintragOut])
def list_dienstplan(
    von: Optional[date] = None,
    bis: Optional[date] = None,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    return repo.list_eintraege(von, bis)


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
