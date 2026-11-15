"""Systemstatus - aktuell nur die Warnung vor möglichen OneDrive-
Synchronisationskonflikten der lokalen Datenbank (siehe datensicherheit.py).
Für Schichtleitung/Admin sichtbar (gleiche Stufe wie Änderungsprotokoll)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..datensicherheit import finde_konfliktkopien, warnungen_text
from ..deps import require_schichtleitung

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/warnungen")
def system_warnungen(role: str = Depends(require_schichtleitung)):
    """Liste aktueller System-Warnungen als Freitext, z. B. erkannte
    Datenbank-Konfliktkopien (siehe datensicherheit.py). Wird im Frontend als
    Hinweisleiste auf der 'Heute'-Seite angezeigt."""
    return {"warnungen": warnungen_text(finde_konfliktkopien())}
