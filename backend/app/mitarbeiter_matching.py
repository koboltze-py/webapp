"""Gemeinsame Hilfsfunktion, um einen Mitarbeiter-Namen (egal ob im
Dienstplan-Format 'Vorname Nachname' oder im Krankmeldungs-Format
'Nachname, Vorname', siehe routers/dienstplan.py:_employee_zu_dienstplan_name)
moeglichst eindeutig einem Datensatz der Mitarbeiter-Stammdaten zuzuordnen.

Das ist die Grundlage der Mitarbeiter-Historie (models.py:MitarbeiterEreignis):
nur mit einer verlaesslichen Zuordnung Name -> mitarbeiter_id laesst sich je
Stammdatensatz nachvollziehen, wie oft jemand krank war.

Erkennt dabei:
  - exakte Treffer (Gross-/Kleinschreibung und Leerzeichen egal)
  - vertauschte Vor-/Nachnamen ("Nachname Vorname" statt "Vorname Nachname")
  - kleinere Tippfehler, per Aehnlichkeitsvergleich (vertauschte/fehlende
    Buchstaben) - aber NUR, wenn der beste Treffer eindeutig und klar besser
    als der zweitbeste ist, siehe MatchErgebnis.fuzzy.
Mehrdeutige oder zu unsichere Faelle liefern bewusst KEINEN Treffer, damit
keine falschen Mitarbeiter-Zuordnungen entstehen - sie muessen manuell
geprueft werden (siehe DienstplanImportResult.unsichere_zuordnungen)."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

# Ab dieser Aehnlichkeit (0..1) wird ein Tippfehler-Treffer ueberhaupt in
# Betracht gezogen.
FUZZY_SCHWELLE = 0.82
# Der beste Treffer muss mindestens um diesen Betrag besser sein als der
# zweitbeste, sonst gilt die Zuordnung als mehrdeutig (kein Treffer).
FUZZY_MINDESTABSTAND = 0.06


@dataclass
class MatchErgebnis:
    mitarbeiter: Any
    fuzzy: bool  # True = nur ueber Tippfehler-/Dreher-Erkennung gefunden, nicht exakt


def _normalisiere(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def zu_dienstplan_format(name: str) -> str:
    """'Nachname, Vorname' -> 'Vorname Nachname'; Namen ohne Komma bleiben
    unveraendert (z. B. bereits im Dienstplan-Format)."""
    if "," in name:
        nachname, _, vorname = name.partition(",")
        return f"{vorname.strip()} {nachname.strip()}".strip()
    return name.strip()


def _mitarbeiter_felder(m: Any) -> tuple[str, str]:
    vorname = m["vorname"] if isinstance(m, dict) else m.vorname
    nachname = m["nachname"] if isinstance(m, dict) else m.nachname
    return (vorname or "").strip(), (nachname or "").strip()


def ordne_mitarbeiter_zu(name: str, mitarbeiter_liste: Iterable[Any]) -> Optional[MatchErgebnis]:
    """Versucht `name` genau einem Eintrag aus `mitarbeiter_liste` (Mitarbeiter-
    ORM-Objekte oder dicts mit vorname/nachname/id) zuzuordnen.

    Reihenfolge: 1) exakter Treffer, 2) vertauschte Vor-/Nachnamen,
    3) eindeutiger Tippfehler-Treffer. Gibt None zurueck, wenn kein,
    mehrdeutiger oder zu unsicherer Treffer gefunden wurde."""
    if not name or not name.strip():
        return None

    kandidaten = list(mitarbeiter_liste)
    ziel = _normalisiere(zu_dienstplan_format(name))
    ziel_vertauscht = None
    teile = ziel.split(" ", 1)
    if len(teile) == 2:
        ziel_vertauscht = f"{teile[1]} {teile[0]}"

    exakt_treffer = []
    vertauscht_treffer = []
    aehnlichkeiten: list[tuple[float, Any]] = []

    for m in kandidaten:
        vorname, nachname = _mitarbeiter_felder(m)
        voller_name = _normalisiere(f"{vorname} {nachname}")
        if voller_name == ziel:
            exakt_treffer.append(m)
            continue
        if ziel_vertauscht and voller_name == ziel_vertauscht:
            vertauscht_treffer.append(m)
            continue
        score = SequenceMatcher(None, voller_name, ziel).ratio()
        aehnlichkeiten.append((score, m))

    if len(exakt_treffer) == 1:
        return MatchErgebnis(exakt_treffer[0], fuzzy=False)
    if len(exakt_treffer) > 1:
        return None  # mehrdeutig (z. B. Namensgleichheit) -> manuell pruefen

    if len(vertauscht_treffer) == 1:
        return MatchErgebnis(vertauscht_treffer[0], fuzzy=True)
    if len(vertauscht_treffer) > 1:
        return None

    if not aehnlichkeiten:
        return None
    aehnlichkeiten.sort(key=lambda t: t[0], reverse=True)
    bester_score, bester = aehnlichkeiten[0]
    zweitbester_score = aehnlichkeiten[1][0] if len(aehnlichkeiten) > 1 else 0.0
    if bester_score >= FUZZY_SCHWELLE and (bester_score - zweitbester_score) >= FUZZY_MINDESTABSTAND:
        return MatchErgebnis(bester, fuzzy=True)
    return None
