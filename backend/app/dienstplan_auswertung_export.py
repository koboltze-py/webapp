"""Excel-Export der Dienstplan-Auswertung (siehe routers/dienstplan.py:
GET /api/dienstplan/auswertung/export) - eine Arbeitsmappe mit zwei
Tabellenblättern (Verspätungen, Krankmeldungen), für einen frei wählbaren
Zeitraum. Nutzt dieselbe Blatt-Schreiblogik wie die übrigen
Protokoll-Exporte (siehe excel_export.py)."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, Sequence

from openpyxl import Workbook

from .excel_export import schreibe_tabellen_blatt


def export_dienstplan_auswertung_excel(
    von: date,
    bis: date,
    verspaetungen: Sequence[dict[str, Any]],
    krankmeldungen: Sequence[dict[str, Any]],
) -> bytes:
    zeitraum = f"{von.strftime('%d.%m.%Y')} - {bis.strftime('%d.%m.%Y')}"
    wb = Workbook()

    ws_verspaetungen = wb.active
    ws_verspaetungen.title = "Verspätungen"
    schreibe_tabellen_blatt(
        ws_verspaetungen,
        titel=f"Verspätungen {zeitraum}",
        spalten=[
            ("datum", "Datum"),
            ("mitarbeiter_name", "Mitarbeiter:in"),
            ("dienst_kategorie", "Dienst"),
            ("geplanter_beginn", "Geplanter Beginn"),
            ("verspaetung_minuten", "Verspätung (Minuten)"),
            ("erfasst_von", "Erfasst von"),
            ("erfasst_am", "Erfasst am"),
        ],
        zeilen=list(verspaetungen),
    )

    ws_krank = wb.create_sheet("Krankmeldungen")
    schreibe_tabellen_blatt(
        ws_krank,
        titel=f"Krankmeldungen {zeitraum}",
        spalten=[
            ("mitarbeiter_name", "Mitarbeiter:in"),
            ("sick_from", "Krank von"),
            ("sick_to", "Krank bis"),
            ("kranktage", "Kranktage"),
            ("accepted_by", "Angenommen von"),
            ("reported_at", "Gemeldet am"),
        ],
        zeilen=list(krankmeldungen),
    )

    puffer = BytesIO()
    wb.save(puffer)
    return puffer.getvalue()
