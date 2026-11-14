"""Export eines Dienstplan-Tages als Excel-Datei im Format der echten
Tagesdienstplan-Vorlage ("CareMan-Dienstplan"). Format wurde direkt gegen
eine echte Datei abgeglichen (04_Tagesdienstpläne\\11_November\\
14.11.2026.xlsx): Spaltenbreiten, Zeilenhöhen, Schriftarten, Zellfarben,
Rahmen, Zahlenformate und Zusammenführungen sind 1:1 übernommen. Einzige
bewusste Abweichung: die Fußzeile verweist auf dieses System statt (fälsch-
licherweise) auf "CareMan-Dienstplan", da die Datei hier erzeugt wurde.
Zellfarben für Krank (rot) und Bulmor-Fahrer:in (gelb) stammen aus unserem
eigenen Datenmodell (ist_krank/ist_bulmorfahrer); die exakte Bedeutung
einzelner, in der Originalvorlage beobachteter Sonderfarben (z. B. Grün an
einzelnen Beginn-Zellen) ließ sich aus einer einzelnen Beispieldatei nicht
zweifelsfrei klären und wird daher nicht nachgebildet."""
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from io import BytesIO
from typing import Any, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

TITEL_FONT = Font(name="Verdana", size=9)
HEADER_FONT = Font(name="Calibri", size=11)
ABSCHNITT_FONT = Font(name="Calibri", size=10, bold=True)
DATEN_FONT = Font(name="Calibri", size=10)

ABSCHNITT_FILL = PatternFill("solid", fgColor="FFB2CCCC")
ZEBRA_FILL = PatternFill("solid", fgColor="FFF5F5F5")
KRANK_FILL = PatternFill("solid", fgColor="FFFF0000")
BULLI_FILL = PatternFill("solid", fgColor="FFFFFF00")
ABWEICHUNG_FILL = PatternFill("solid", fgColor="FFFFC000")

DUENNER_RAHMEN = Side(style="thin")
BOX_RAHMEN = Border(top=DUENNER_RAHMEN, bottom=DUENNER_RAHMEN, left=DUENNER_RAHMEN, right=DUENNER_RAHMEN)

SPALTENBREITEN = {"A": 0.18, "B": 2.45, "C": 11.45, "D": 28.54, "E": 3.27, "F": 0.27, "G": 6.45, "H": 8.18, "I": 8.18, "J": 17.18, "K": 5.45}
HEADER_ZEILE = 4
ERSTE_DATENZEILE = 5


def _zeit_wert(hhmm: Optional[str]) -> Optional[dt_time]:
    if not hhmm or ":" not in hhmm:
        return None
    try:
        h, m = hhmm.split(":")
        return dt_time(int(h), int(m))
    except ValueError:
        return None


def _name_zu_nachname_vorname(mitarbeiter_name: str) -> str:
    """Kehrt das Dienstplan-Anzeigeformat ('Vorname Nachname') wieder in
    das Original-Format ('Nachname, Vorname') um - symmetrisch zu
    dienstplan_parser._parse_name (erstes Wort = Vorname, Rest = Nachname)."""
    teile = (mitarbeiter_name or "").strip().split(" ", 1)
    if len(teile) == 2:
        return f"{teile[1]}, {teile[0]}"
    return mitarbeiter_name or ""


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


def _box(ws: Any, zeile: int, spalten: str = "BCDEFGHIJK") -> None:
    for spalte in spalten:
        ws[f"{spalte}{zeile}"].border = BOX_RAHMEN


def export_dienstplan_excel(tag: date, eintraege: list[dict[str, Any]], ersteller: str = "") -> bytes:
    """eintraege: bereits kategorisierte+sortierte Liste (siehe
    dienstplan_sortierung.kategorisiere_und_sortiere), wie sie auch das
    GET /api/dienstplan-Endpunkt liefert."""
    wb = Workbook()
    ws = wb.active
    ws.title = tag.strftime("%d.%m.%Y")
    ws.sheet_view.showGridLines = False

    for spalte, breite in SPALTENBREITEN.items():
        ws.column_dimensions[spalte].width = breite
    ws.row_dimensions[1].height = 15.75
    ws.row_dimensions[2].height = 25.5
    ws.row_dimensions[3].height = 15.75
    ws.row_dimensions[HEADER_ZEILE].height = 30.0

    # Titelzeile: Datumsbereich links, "Ersteller" rechts (wie im Original
    # die CareMan-Benutzerkennung).
    ws.merge_cells("A2:E2")
    ws["A2"] = f"Mitarbeiter im Dienst pro Tag ({tag.strftime('%d.%m.%Y')} - {(tag + timedelta(days=1)).strftime('%d.%m.%Y')})"
    ws["A2"].font = TITEL_FONT
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells("G2:K2")
    ws["G2"] = f"DRK FKB Krankmeldungen/Dienstplan - {ersteller}" if ersteller else "DRK FKB Krankmeldungen/Dienstplan"
    ws["G2"].font = TITEL_FONT
    ws["G2"].alignment = Alignment(horizontal="right", vertical="center")

    # Header-Zeile: Datum (B:C zusammengeführt), Name, Dienst (E:G
    # zusammengeführt), Beginn, Ende, Ebene.
    ws.merge_cells(f"B{HEADER_ZEILE}:C{HEADER_ZEILE}")
    ws.merge_cells(f"E{HEADER_ZEILE}:G{HEADER_ZEILE}")
    for spalte, text in (("B", "Datum"), ("D", "Name"), ("E", "Dienst"), ("H", "Beginn"), ("I", "Ende"), ("J", "Ebene")):
        zelle = ws[f"{spalte}{HEADER_ZEILE}"]
        zelle.value = text
        zelle.font = HEADER_FONT
        zelle.alignment = Alignment(horizontal="center", vertical="center")
    _box(ws, HEADER_ZEILE)

    nach_abschnitt: dict[str, list[dict[str, Any]]] = {}
    for eintrag in eintraege:
        nach_abschnitt.setdefault(_abschnitt(eintrag), []).append(eintrag)

    zeile = ERSTE_DATENZEILE
    zebra_index = 0
    for abschnitt in ("[Stamm FH]", "Bulmor", "Dispo"):
        gruppe = nach_abschnitt.get(abschnitt)
        if not gruppe:
            continue
        ws.row_dimensions[zeile].height = 16.5
        ws.merge_cells(f"B{zeile}:J{zeile}")
        zelle = ws[f"B{zeile}"]
        zelle.value = f"[{abschnitt}]  " if abschnitt == "Stamm FH" else f"{abschnitt}  "
        zelle.font = ABSCHNITT_FONT
        zelle.fill = ABSCHNITT_FILL
        zelle.alignment = Alignment(horizontal="left", vertical="center")
        zeile += 1

        for eintrag in gruppe:
            ws.row_dimensions[zeile].height = 27.75
            zeilen_fill = ZEBRA_FILL if zebra_index % 2 == 0 else None
            zebra_index += 1

            # Anders als die Kopfzeile (B4:C4 zusammengeführt) ist die
            # Datum-Spalte in den Datenzeilen NICHT zusammengeführt - der
            # Wert steht allein in Spalte C, Spalte B bleibt leer (so auch
            # im Original).
            ws[f"C{zeile}"] = datetime.combine(tag, dt_time(0, 0))
            ws[f"C{zeile}"].number_format = r"dd\.mm\.yy"

            ws[f"D{zeile}"] = _name_zu_nachname_vorname(eintrag.get("mitarbeiter_name", ""))

            ws.merge_cells(f"E{zeile}:G{zeile}")
            dienst_zelle = ws[f"E{zeile}"]
            dienst_zelle.value = "Krank" if eintrag.get("ist_krank") else (eintrag.get("dienst_kategorie") or "")
            if eintrag.get("ist_krank"):
                dienst_zelle.fill = KRANK_FILL
            elif eintrag.get("ist_bulmorfahrer"):
                dienst_zelle.fill = BULLI_FILL

            beginn = _zeit_wert(eintrag.get("start_zeit"))
            ende = _zeit_wert(eintrag.get("end_zeit"))
            if beginn is not None:
                ws[f"H{zeile}"] = beginn
                ws[f"H{zeile}"].number_format = "h:mm"
            if ende is not None:
                ws[f"I{zeile}"] = ende
                ws[f"I{zeile}"].number_format = "h:mm"
            if eintrag.get("zeit_abweichend"):
                if ws[f"H{zeile}"].fill.fgColor.rgb in (None, "00000000"):
                    ws[f"H{zeile}"].fill = ABWEICHUNG_FILL
                if ws[f"I{zeile}"].fill.fgColor.rgb in (None, "00000000"):
                    ws[f"I{zeile}"].fill = ABWEICHUNG_FILL

            ws[f"J{zeile}"] = "Abweichung" if eintrag.get("zeit_abweichend") else "Dienstplan"
            if eintrag.get("notiz"):
                ws[f"K{zeile}"] = eintrag["notiz"]

            for spalte in "BCDEFGHIJK":
                z = ws[f"{spalte}{zeile}"]
                z.font = DATEN_FONT
                z.alignment = Alignment(horizontal="left", vertical="center")
                if zeilen_fill is not None and (z.fill is None or z.fill.fgColor.rgb in (None, "00000000")):
                    z.fill = zeilen_fill
            _box(ws, zeile)
            zeile += 1

    fuss_zeile = zeile
    ws.merge_cells(f"A{fuss_zeile}:E{fuss_zeile}")
    ws[f"A{fuss_zeile}"] = f"{datetime.now().strftime('%d.%m.%y %H:%M:%S')} - DRK FKB Krankmeldungen/Dienstplan-Export"
    ws[f"A{fuss_zeile}"].font = TITEL_FONT
    ws.merge_cells(f"G{fuss_zeile}:K{fuss_zeile}")
    ws[f"G{fuss_zeile}"] = "1 / 1"
    ws[f"G{fuss_zeile}"].font = TITEL_FONT

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
