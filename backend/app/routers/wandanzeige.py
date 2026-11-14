"""Öffentlicher, nur-lesender Endpunkt für die Wandanzeige (kein Login,
keine Navigation - siehe frontend/wandanzeige.html). Zeigt ausschließlich
Daten aus dem Dienstplan-Import (nicht aus den Krankmeldungen), damit keine
zusätzlichen Zugriffsrechte auf die Krankmeldungs-Tabelle nötig sind."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from ..modules_repository import list_dienstplan_oeffentlich

router = APIRouter(prefix="/api/wandanzeige", tags=["wandanzeige"])


@router.get("/heute")
def wandanzeige_heute():
    tag = date.today()
    eintraege = list_dienstplan_oeffentlich(tag)
    return {
        "datum": tag.isoformat(),
        "eintraege": eintraege,
        "anzahl_krank": sum(1 for e in eintraege if e["ist_krank"]),
        "anzahl_bulmorfahrer": sum(1 for e in eintraege if e["ist_bulmorfahrer"]),
    }
