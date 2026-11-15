"""Tagesprotokoll: ein fortlaufendes, für Menschen lesbares Änderungs-Log je
Tag (Backups\\Tagesprotokoll\\<Jahr>\\<MM>_<Monat>\\<Tag>.xlsx) - analog zu den
automatischen Tagesdienstplan-Backups (siehe routers/dienstplan.py), aber als
WACHSENDES Protokoll gedacht: jede Änderung wird als neue Zeile angehängt,
nichts wird überschrieben (anders als der Tagesdienstplan-Schnappschuss, der
je Tag nur den aktuellen Stand zeigt).

Schreiben ist bewusst "best effort": ein Fehler hier darf keine eigentliche
Operation verhindern (gleiches Prinzip wie aktivitaet.py/mitarbeiter_historie.py)."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

HEADER = ["Zeitpunkt", "Aktion", "Mitarbeiter", "Durchgeführt von", "Rolle", "Beschreibung"]


def _ordner(basis: Path, tag: date) -> Path:
    return basis / str(tag.year) / f"{tag.month:02d}_{MONATSNAMEN[tag.month - 1]}"


def pfad(basis: Path, tag: date) -> Path:
    return _ordner(basis, tag) / f"{tag.strftime('%d.%m.%Y')}.xlsx"


def protokolliere(
    basis: Path,
    tag: date,
    *,
    aktion: str,
    mitarbeiter_name: str = "",
    actor_username: str = "",
    actor_role: str = "",
    beschreibung: str = "",
) -> None:
    """Hängt eine Zeile an das Tagesprotokoll von `tag` an (legt Datei/Ordner
    bei Bedarf an). Ein Fehler hierbei darf die eigentliche Operation nicht
    verhindern, siehe Modul-Docstring."""
    try:
        datei = pfad(basis, tag)
        datei.parent.mkdir(parents=True, exist_ok=True)
        if datei.exists():
            wb = load_workbook(datei)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Tagesprotokoll"
            ws.append(HEADER)
        ws.append([
            datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            aktion,
            mitarbeiter_name,
            actor_username,
            actor_role,
            beschreibung,
        ])
        wb.save(datei)
    except Exception:  # noqa: BLE001 - Protokoll ist best-effort
        pass
