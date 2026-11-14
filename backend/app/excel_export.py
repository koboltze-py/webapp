"""Einfacher, wiederverwendbarer Excel-Export für tabellarische Protokolle
(Mitarbeiter-Historie, Benutzer-Aktivitätsprotokoll, siehe routers/mitarbeiter.py
und routers/audit.py) - bewusst schlicht gehalten (anders als
dienstplan_export.py, das die echte Tagesdienstplan-Vorlage nachbildet)."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF4A6274")
DATEN_FONT = Font(name="Calibri", size=10)


def export_tabelle_excel(
    *,
    titel: str,
    blattname: str,
    spalten: Sequence[tuple[str, str]],
    zeilen: Sequence[dict[str, Any]],
) -> bytes:
    """Erzeugt eine .xlsx-Datei mit genau einem Tabellenblatt.

    `spalten` ist eine Liste aus (Schlüssel-in-zeilen, Spaltentitel);
    Werte vom Typ datetime/date werden automatisch als lokal lesbare
    Zeichenkette formatiert, dict/list-Werte als JSON-Text."""
    wb = Workbook()
    ws = wb.active
    ws.title = blattname[:31] or "Export"

    ws.append([titel])
    ws["A1"].font = Font(name="Calibri", size=13, bold=True)
    ws.append([f"Exportiert am {datetime.now().strftime('%d.%m.%Y %H:%M')} · {len(zeilen)} Einträge"])
    ws["A2"].font = Font(name="Calibri", size=9, italic=True, color="FF666666")
    ws.append([])

    header_zeile = 4
    for col_idx, (_, titel_spalte) in enumerate(spalten, start=1):
        zelle = ws.cell(row=header_zeile, column=col_idx, value=titel_spalte)
        zelle.font = HEADER_FONT
        zelle.fill = HEADER_FILL
        zelle.alignment = Alignment(vertical="center")
    ws.freeze_panes = ws.cell(row=header_zeile + 1, column=1)

    for row_idx, zeile in enumerate(zeilen, start=header_zeile + 1):
        for col_idx, (schluessel, _) in enumerate(spalten, start=1):
            wert = zeile.get(schluessel)
            if isinstance(wert, datetime):
                wert = wert.strftime("%d.%m.%Y %H:%M:%S")
            elif isinstance(wert, date):
                wert = wert.strftime("%d.%m.%Y")
            elif isinstance(wert, (dict, list)):
                import json

                wert = json.dumps(wert, ensure_ascii=False, default=str) if wert else ""
            elif wert is None:
                wert = ""
            zelle = ws.cell(row=row_idx, column=col_idx, value=wert)
            zelle.font = DATEN_FONT
            zelle.alignment = Alignment(vertical="top", wrap_text=False)

    for col_idx, (schluessel, titel_spalte) in enumerate(spalten, start=1):
        laenge = max(
            [len(titel_spalte)]
            + [len(str(z.get(schluessel, ""))) for z in zeilen[:500]]  # Performance bei sehr langen Listen
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(laenge + 2, 10), 60)

    puffer = BytesIO()
    wb.save(puffer)
    return puffer.getvalue()
