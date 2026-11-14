"""Export eines Dienstplan-Tages als Excel-Datei, angelehnt an die echte
Tagesdienstplan-Vorlage ("CareMan-Dienstplan", siehe Vorlagen unter
04_Tagesdienstpläne): Titelzeile, Header NAME/DIENST/BEGINN/ENDE/EBENE in
Zeile 4, Abschnitts-Überschriften in Spalte B ("[Stamm FH]"/"Bulmor"/
"Dispo"). Keine pixelgenaue Kopie (Logo, exakte Zellfarben/-breiten der
Originalvorlage liegen uns nicht vor), aber dieselbe Spaltenbelegung,
Reihenfolge und Abschnittsgliederung, sodass die Datei vertraut aussieht
und in Excel genauso weiterverwendet werden kann."""
from __future__ import annotations

from datetime import date, datetime, time as dt_time
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
ABSCHNITT_FILL = PatternFill("solid", fgColor="B2CCCC")
HEADER_FONT = Font(bold=True)
TITEL_FONT = Font(bold=True, size=14)


def _zeit_wert(hhmm: str | None) -> dt_time | None:
    if not hhmm or ":" not in hhmm:
        return None
    try:
        h, m = hhmm.split(":")
        return dt_time(int(h), int(m))
    except ValueError:
        return None


def _abschnitt(eintrag: dict[str, Any]) -> str:
    """Grobe Zuordnung zum Original-Abschnitt anhand der uns vorliegenden
    Felder (echte Abschnittszugehörigkeit wird beim Import nicht
    gespeichert): 'B1' = Bulmor (siehe dienstplan_parser-Validierung gegen
    echte Dateien), ist_dispo = Dispo-Abschnitt, alles andere Stamm FH."""
    if (eintrag.get("dienst_kategorie") or "").strip().upper() == "B1":
        return "Bulmor"
    if eintrag.get("ist_dispo"):
        return "Dispo"
    return "[Stamm FH]"


def export_dienstplan_excel(tag: date, eintraege: list[dict[str, Any]]) -> bytes:
    """eintraege: bereits kategorisierte+sortierte Liste (siehe
    dienstplan_sortierung.kategorisiere_und_sortiere), wie sie auch das
    GET /api/dienstplan-Endpunkt liefert."""
    wb = Workbook()
    ws = wb.active
    ws.title = tag.strftime("%d.%m.%Y")

    ws["A2"] = f"Mitarbeiter im Dienst pro Tag {tag.strftime('%d.%m.%Y')}"
    ws["A2"].font = TITEL_FONT

    header_zeile = 4
    spalten = {"datum": "B", "name": "D", "dienst": "E", "beginn": "H", "ende": "I", "ebene": "J", "notiz": "K"}
    beschriftungen = {"datum": "Datum", "name": "Name", "dienst": "Dienst", "beginn": "Beginn", "ende": "Ende", "ebene": "Ebene", "notiz": "Notiz"}
    for schluessel, spalte in spalten.items():
        zelle = ws[f"{spalte}{header_zeile}"]
        zelle.value = beschriftungen[schluessel]
        zelle.font = HEADER_FONT
        zelle.fill = HEADER_FILL

    zeile = header_zeile + 1
    aktueller_abschnitt: str | None = None
    # Reihenfolge der Einträge (sortier_rang) bleibt erhalten; Abschnitte
    # werden beim Wechsel neu eingefügt, analog zur Original-Vorlage.
    nach_abschnitt: dict[str, list[dict[str, Any]]] = {}
    for eintrag in eintraege:
        nach_abschnitt.setdefault(_abschnitt(eintrag), []).append(eintrag)

    for abschnitt in ("[Stamm FH]", "Bulmor", "Dispo"):
        gruppe = nach_abschnitt.get(abschnitt)
        if not gruppe:
            continue
        zelle = ws[f"B{zeile}"]
        zelle.value = abschnitt
        zelle.font = HEADER_FONT
        zelle.fill = ABSCHNITT_FILL
        zeile += 1
        for eintrag in gruppe:
            ws[f"B{zeile}"] = datetime.combine(tag, dt_time(0, 0))
            ws[f"B{zeile}"].number_format = "DD.MM.YYYY"
            ws[f"D{zeile}"] = eintrag.get("mitarbeiter_name", "")
            ws[f"E{zeile}"] = "Krank" if eintrag.get("ist_krank") else (eintrag.get("dienst_kategorie") or "")
            beginn = _zeit_wert(eintrag.get("start_zeit"))
            ende = _zeit_wert(eintrag.get("end_zeit"))
            if beginn is not None:
                ws[f"H{zeile}"] = beginn
                ws[f"H{zeile}"].number_format = "HH:MM"
            if ende is not None:
                ws[f"I{zeile}"] = ende
                ws[f"I{zeile}"].number_format = "HH:MM"
            ws[f"J{zeile}"] = "Abweichung" if eintrag.get("zeit_abweichend") else "Dienstplan"
            ws[f"K{zeile}"] = eintrag.get("notiz") or ""
            zeile += 1

    ws[f"A{zeile + 1}"] = f"Export DRK FKB Krankmeldungen/Dienstplan · {datetime.now().strftime('%d.%m.%y %H:%M:%S')}"
    for spalte, breite in {"A": 4, "B": 12, "C": 4, "D": 26, "E": 10, "F": 4, "G": 4, "H": 9, "I": 9, "J": 12, "K": 34}.items():
        ws.column_dimensions[spalte].width = breite
    ws["A2"].alignment = Alignment(horizontal="left")

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
