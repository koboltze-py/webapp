"""Sortierung und Kategorisierung von Dienstplan-Einträgen.

Setzt die vom Nutzer vorgegebene Standard-Sortierung um:
  T < T10 < T8 < (sonstige Tagdienste) < N < N10 < DT < DT3 < DN < DN3

Kranke Mitarbeitende werden anhand ihrer tatsächlich eingetragenen
Dienstzeiten (Beginn/Ende) derselben Kategorie zugeordnet wie reguläre
Einträge - dieselben Referenzzeiten wie im Nesk3-Projekt
(..\\..\\Nesk\\Nesk3\\functions\\dienstplan_parser.py, _ermittle_krank_typ):

  T    06:00-18:00   T10  09:00-19:00   T8   10:00-18:00
  DT   07:00-19:00
  N    18:00-06:00   N10  21:00-07:00
  DN/DN3/DT3 teilen sich dieselbe Zeit (19:00-07:00) - ohne weiteres
  Unterscheidungsmerkmal wird hier auf 'DN' zurückgefallen, wie im
  Original-Parser dokumentiert ("Zeiten identisch").

Mitarbeitende mit von ihrer Kategorie abweichenden Zeiten werden als
"zeit_abweichend" markiert (nur möglich, wenn die Kategorie bekannt ist).
"""
from __future__ import annotations

from typing import Any, Optional

# Referenzzeiten je Dienst-Kürzel (Beginn, Ende), siehe Docstring oben.
KANONISCHE_ZEITEN: dict[str, tuple[str, str]] = {
    "T": ("06:00", "18:00"),
    "T10": ("09:00", "19:00"),
    "T8": ("10:00", "18:00"),
    "DT": ("07:00", "19:00"),
    "N": ("18:00", "06:00"),
    "N10": ("21:00", "07:00"),
    "DN": ("19:00", "07:00"),
    "DN3": ("19:00", "07:00"),
    "DT3": ("19:00", "07:00"),
}

# Sortierrang je Kategorie (siehe Vorgabe: T < T10 < T8 < sonstige Tagdienste
# < N < N10 < DT < DT3 < DN < DN3). DT/DT3/DN/DN3 = Dispo (optisch abgesetzt).
SORTIER_RANG: dict[str, int] = {
    "T": 10, "T10": 20, "T8": 30,
    "N": 50, "N10": 60,
    "DT": 70, "DT3": 80, "DN": 90, "DN3": 100,
}
RANG_SONSTIGE_TAG = 40
RANG_SONSTIGE_NACHT = 65
RANG_UNBEKANNT = 999

DISPO_KATEGORIEN = frozenset({"DT", "DT3", "DN", "DN3"})


def _stunde(zeit: Optional[str]) -> Optional[int]:
    if not zeit or ":" not in zeit:
        return None
    try:
        return int(zeit.split(":")[0])
    except ValueError:
        return None


def _match_kanonische_kategorie(start_zeit: Optional[str], end_zeit: Optional[str]) -> Optional[str]:
    """Versucht, Beginn/Ende exakt einer bekannten Kategorie zuzuordnen
    (für Krankmeldungen ohne eigenes Dienstkürzel)."""
    if not start_zeit:
        return None
    for kategorie, (ref_start, ref_end) in KANONISCHE_ZEITEN.items():
        if start_zeit == ref_start and end_zeit == ref_end:
            # DN/DN3/DT3 teilen sich dieselbe Zeit -> einheitlich 'DN' (siehe Docstring).
            if kategorie in ("DN3", "DT3"):
                return "DN"
            return kategorie
    return None


def kategorisiere_eintrag(eintrag: dict[str, Any]) -> dict[str, Any]:
    """Ergänzt einen Dienstplan-Eintrag (dict mit mind. dienst_kategorie,
    start_zeit, end_zeit, ist_krank) um:
      - effektive_kategorie: die für die Sortierung verwendete Kategorie
      - sortier_rang: numerischer Rang für die Standard-Sortierung
      - ist_dispo: True für DT/DT3/DN/DN3 (optisch abgesetzt darzustellen)
      - zeit_abweichend: True, wenn Beginn/Ende von der Referenzzeit der
        (effektiven) Kategorie abweichen
    Gibt ein NEUES dict zurück (Original bleibt unverändert)."""
    ergebnis = dict(eintrag)
    start_zeit = eintrag.get("start_zeit")
    end_zeit = eintrag.get("end_zeit")
    ist_krank = bool(eintrag.get("ist_krank"))

    if ist_krank:
        kategorie = _match_kanonische_kategorie(start_zeit, end_zeit)
    else:
        rohkategorie = (eintrag.get("dienst_kategorie") or "").strip().upper() or None
        kategorie = rohkategorie if rohkategorie in SORTIER_RANG else None
        # Unbekannte, aber im System vorhandene Kategorien (z. B. Tippfehler)
        # werden unten über die Uhrzeit grob eingeordnet, nicht verworfen.
        if rohkategorie and kategorie is None:
            ergebnis.setdefault("dienst_kategorie", rohkategorie)

    if kategorie in SORTIER_RANG:
        rang = SORTIER_RANG[kategorie]
        ref_start, ref_end = KANONISCHE_ZEITEN[kategorie if kategorie in KANONISCHE_ZEITEN else "DN"]
        zeit_abweichend = bool(start_zeit) and (start_zeit != ref_start or (end_zeit or None) != ref_end)
    else:
        stunde = _stunde(start_zeit)
        if stunde is None:
            rang = RANG_UNBEKANNT
        elif 5 <= stunde < 15:
            rang = RANG_SONSTIGE_TAG
        else:
            rang = RANG_SONSTIGE_NACHT
        zeit_abweichend = False  # keine Referenzzeit vorhanden -> kein Vergleich möglich

    ergebnis["effektive_kategorie"] = kategorie
    ergebnis["sortier_rang"] = rang
    ergebnis["ist_dispo"] = kategorie in DISPO_KATEGORIEN
    ergebnis["zeit_abweichend"] = zeit_abweichend
    return ergebnis


def kategorisiere_und_sortiere(eintraege: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wendet kategorisiere_eintrag auf alle Einträge an und sortiert sie in
    der geforderten Standard-Reihenfolge (Rang, dann Beginn, dann Name)."""
    annotiert = [kategorisiere_eintrag(e) for e in eintraege]
    annotiert.sort(key=lambda e: (e["sortier_rang"], e.get("start_zeit") or "99:99", e.get("mitarbeiter_name") or ""))
    return annotiert
