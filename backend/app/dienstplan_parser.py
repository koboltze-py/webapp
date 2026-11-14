"""Parser für Tagesdienstplan-Excel-Dateien.

Vereinfacht abgeleitet aus dem Dienstplan-Parser des Nesk3-Projekts
(..\\..\\Nesk\\Nesk3\\functions\\dienstplan_parser.py). Übernommen wird die
generische Erkennungslogik:

  - Header-Zeile (Spalten NAME, DIENST, optional BEGINN/ENDE) wird innerhalb
    der ersten 20 Zeilen gesucht.
  - "Krank" wird rein über den Zelltext der DIENST-Spalte erkannt (KRANK/K).
  - Gelb hinterlegte Zellen (Name- oder Dienst-Spalte) markieren
    Bulli-Fahrer:innen (derselbe Gelb-Bereich FFFF00-FFFF4F wie in Nesk3).
  - Dienstzeiten werden aus BEGINN/ENDE gelesen (Excel-Zeitwert, datetime,
    time-Objekt oder "HH:MM"-Text).

Bewusst NICHT übernommen wurden die Nesk3-spezifischen Geschäftsregeln
(Betreuer-/Dispo-Abschnitte, bedingtes Runden auf volle Stunden, fest
ausgeschlossene Namen) - diese sind an die andere Dienstplan-Struktur von
Nesk3 gebunden und für die Erste-Hilfe-Station nicht ohne Weiteres gültig.
Bei Bedarf kann das anhand echter Beispiel-Dateien ergänzt werden.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl.utils.datetime import from_excel

KRANK_WERTE = ("KRANK", "K")


def _check_cell_color(*cell_objs: Any) -> bool:
    """True, wenn eine der übergebenen Zellen gelb hinterlegt ist
    (Bulli-Fahrer-Markierung, Bereich FFFF00-FFFF4F wie in Nesk3)."""
    for cell_obj in cell_objs:
        fill = getattr(cell_obj, "fill", None)
        if not fill or fill.patternType not in ("solid", "solidFill"):
            continue
        fg = getattr(fill, "fgColor", None)
        rgb = getattr(fg, "rgb", None) if fg else None
        if not rgb:
            continue
        color_hex = str(rgb).upper()
        if len(color_hex) >= 8:
            rr_gg, bb = color_hex[2:6], color_hex[6:8]
        elif len(color_hex) == 6:
            rr_gg, bb = color_hex[0:4], color_hex[4:6]
        else:
            continue
        try:
            if rr_gg == "FFFF" and int(bb, 16) <= 0x4F:
                return True
        except ValueError:
            continue
    return False


def _parse_name(name_text: str) -> Optional[tuple[str, str]]:
    """Parst 'Nachname, Vorname' oder 'Vorname Nachname' -> (vorname, nachname)."""
    name_text = re.sub(r"[^\w\säöüÄÖÜß\-,]", "", name_text.strip())
    if "," in name_text:
        parts = name_text.split(",")
        if len(parts) == 2:
            nachname = parts[0].strip()
            vorname_teil = parts[1].strip().split()
            if nachname and vorname_teil:
                return vorname_teil[0], nachname
        return None
    parts = name_text.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return None


def _parse_time(value: Any) -> Optional[str]:
    """Parst einen Zeitwert (datetime/time/Excel-Zahl/Text) zu 'HH:MM'."""
    try:
        if isinstance(value, datetime):
            t = value.time()
        elif isinstance(value, dt_time):
            t = value
        elif isinstance(value, (int, float)):
            converted = from_excel(value)
            if not isinstance(converted, dt_time):
                return None
            t = converted
        elif isinstance(value, str):
            value = value.strip()
            m = re.match(r"(\d{1,2}):(\d{2})", value)
            if not m:
                m = re.match(r"(\d{2})(\d{2})", value)
            if not m:
                return None
            t = dt_time(int(m.group(1)), int(m.group(2)))
        else:
            return None
        return f"{t.hour:02d}:{t.minute:02d}"
    except Exception:
        return None


def _find_datum(sheet, header_row: int) -> Optional[date]:
    """Sucht in den Zeilen oberhalb des Headers nach einem Datum."""
    for row_idx in range(1, header_row):
        for cell in sheet[row_idx]:
            val = cell.value
            if isinstance(val, datetime):
                return val.date()
            if isinstance(val, str):
                m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", val)
                if m:
                    day, month, year = (int(x) for x in m.groups())
                    if year < 100:
                        year += 2000
                    try:
                        return date(year, month, day)
                    except ValueError:
                        continue
                m = re.search(r"(\d{4})-(\d{2})-(\d{2})", val)
                if m:
                    try:
                        return date(*(int(x) for x in m.groups()))
                    except ValueError:
                        continue
    return None


def parse_dienstplan_excel(file_path: str | Path) -> dict[str, Any]:
    """Liest eine Tagesdienstplan-Excel-Datei ein.

    Rückgabe:
        {
            "success": bool,
            "datum": date | None,
            "eintraege": [
                {
                    "vorname": str, "nachname": str, "mitarbeiter_name": str,
                    "dienst_kategorie": str | None,
                    "start_zeit": str | None, "end_zeit": str | None,
                    "ist_krank": bool, "ist_bulmorfahrer": bool, "notiz": str,
                }, ...
            ],
            "unbekannte_dienste": [str, ...],
            "error": str | None,
        }
    """
    tmp_file: Optional[str] = None
    workbook = None
    try:
        # Datei in temp-Kopie lesen - umgeht Windows-/OneDrive-Dateisperren.
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
            tmp_file = tf.name
        shutil.copy2(file_path, tmp_file)
        workbook = openpyxl.load_workbook(tmp_file, data_only=True)
        sheet = workbook.active

        column_map = None
        header_row = None
        for row_idx in range(1, min(20, sheet.max_row + 1)):
            row_values = [cell.value for cell in sheet[row_idx]]
            name_idx = dienst_idx = beginn_idx = ende_idx = None
            for col_idx, value in enumerate(row_values):
                if isinstance(value, str):
                    v = value.strip().upper()
                    if v == "NAME":
                        name_idx = col_idx
                    elif v == "DIENST":
                        dienst_idx = col_idx
                    elif v == "BEGINN":
                        beginn_idx = col_idx
                    elif v == "ENDE":
                        ende_idx = col_idx
            if name_idx is not None and dienst_idx is not None:
                column_map = {"name": name_idx, "dienst": dienst_idx, "beginn": beginn_idx, "ende": ende_idx}
                header_row = row_idx
                break

        if not column_map:
            return {
                "success": False,
                "datum": None,
                "eintraege": [],
                "unbekannte_dienste": [],
                "error": "Header-Zeile nicht gefunden (benötigt: NAME, DIENST).",
            }

        eintraege: list[dict[str, Any]] = []
        unbekannte_dienste: set[str] = set()
        bekannte_kuerzel = {"T", "N", "DT", "DN"}

        for row in sheet.iter_rows(min_row=header_row + 1, values_only=False):
            row_list = list(row)
            cells = [cell.value for cell in row_list]
            if column_map["name"] >= len(cells):
                continue

            name_cell = cells[column_map["name"]]
            if not name_cell or not isinstance(name_cell, str):
                continue
            parsed_name = _parse_name(name_cell)
            if not parsed_name:
                continue
            vorname, nachname = parsed_name

            name_cell_obj = row_list[column_map["name"]]
            dienst_cell_obj = row_list[column_map["dienst"]] if column_map["dienst"] < len(row_list) else None
            ist_bulmorfahrer = _check_cell_color(name_cell_obj, dienst_cell_obj)

            raw_dienst = cells[column_map["dienst"]] if column_map["dienst"] < len(cells) else None
            dienst_text = str(raw_dienst).strip().upper() if raw_dienst else None
            ist_krank = dienst_text in KRANK_WERTE if dienst_text else False
            dienst_kategorie = None
            if dienst_text and not ist_krank:
                dienst_kategorie = dienst_text
                if dienst_text not in bekannte_kuerzel:
                    unbekannte_dienste.add(dienst_text)

            start_zeit = end_zeit = None
            if column_map["beginn"] is not None and column_map["beginn"] < len(cells):
                start_zeit = _parse_time(cells[column_map["beginn"]])
            if column_map["ende"] is not None and column_map["ende"] < len(cells):
                end_zeit = _parse_time(cells[column_map["ende"]])

            notiz = ""
            if column_map["ende"] is not None:
                notiz_parts = [
                    str(cells[ci]).strip()
                    for ci in range(column_map["ende"] + 1, len(cells))
                    if isinstance(cells[ci], str) and cells[ci].strip()
                ]
                notiz = "  |  ".join(notiz_parts)

            eintraege.append(
                {
                    "vorname": vorname,
                    "nachname": nachname,
                    "mitarbeiter_name": f"{vorname} {nachname}",
                    "dienst_kategorie": dienst_kategorie,
                    "start_zeit": start_zeit,
                    "end_zeit": end_zeit,
                    "ist_krank": ist_krank,
                    "ist_bulmorfahrer": ist_bulmorfahrer,
                    "notiz": notiz,
                }
            )

        return {
            "success": True,
            "datum": _find_datum(sheet, header_row),
            "eintraege": eintraege,
            "unbekannte_dienste": sorted(unbekannte_dienste),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - Importfehler sollen als Ergebnis zurückkommen, nicht crashen
        return {"success": False, "datum": None, "eintraege": [], "unbekannte_dienste": [], "error": str(exc)}
    finally:
        if workbook is not None:
            workbook.close()
        if tmp_file:
            Path(tmp_file).unlink(missing_ok=True)
