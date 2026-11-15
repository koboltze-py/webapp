"""Erkennung vermutlich doppelt angelegter Mitarbeiter-Stammdatensätze
(z. B. durch Tippfehler beim manuellen Anlegen), siehe
routers/mitarbeiter.py: GET /api/mitarbeiter/duplikate.

Nutzt denselben Ähnlichkeitsvergleich (SequenceMatcher) wie
mitarbeiter_matching.py, hier aber Mitarbeiter GEGENEINANDER verglichen statt
gegen einen Dienstplan-Namen. Liefert reine Vorschläge zur manuellen Prüfung
- nichts wird automatisch verändert oder gelöscht."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Iterable

# Etwas grosszuegiger als die Dienstplan-Zuordnung (mitarbeiter_matching.py:
# FUZZY_SCHWELLE = 0.82), da hier bewusst nur VORSCHLÄGE erzeugt werden, die
# ein Mensch bestätigen/verwerfen muss - keine automatische Zuordnung.
AEHNLICHKEITS_SCHWELLE = 0.84


def _normalisiere(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def _voller_name(m: Any) -> str:
    vorname = m["vorname"] if isinstance(m, dict) else m.vorname
    nachname = m["nachname"] if isinstance(m, dict) else m.nachname
    return _normalisiere(f"{vorname or ''} {nachname or ''}")


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.eltern = list(range(n))

    def find(self, i: int) -> int:
        while self.eltern[i] != i:
            self.eltern[i] = self.eltern[self.eltern[i]]
            i = self.eltern[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.eltern[ra] = rb


def finde_duplikat_gruppen(mitarbeiter_liste: Iterable[Any]) -> list[dict[str, Any]]:
    """Gruppiert Mitarbeiter mit exakt gleichem oder sehr ähnlichem Namen.
    Gibt eine Liste von {"grund": "exakt"|"aehnlich", "mitarbeiter": [...]}
    zurück (nur Gruppen mit mindestens 2 Einträgen)."""
    kandidaten = list(mitarbeiter_liste)
    namen = [_voller_name(m) for m in kandidaten]
    n = len(kandidaten)
    uf = _UnionFind(n)
    gruende: dict[tuple[int, int], str] = {}

    for i in range(n):
        for j in range(i + 1, n):
            if not namen[i] or not namen[j]:
                continue
            if namen[i] == namen[j]:
                uf.union(i, j)
                gruende[(i, j)] = "exakt"
            else:
                score = SequenceMatcher(None, namen[i], namen[j]).ratio()
                if score >= AEHNLICHKEITS_SCHWELLE:
                    uf.union(i, j)
                    gruende.setdefault((i, j), "aehnlich")

    gruppen_nach_wurzel: dict[int, list[int]] = {}
    for i in range(n):
        gruppen_nach_wurzel.setdefault(uf.find(i), []).append(i)

    ergebnis: list[dict[str, Any]] = []
    for mitglieder in gruppen_nach_wurzel.values():
        if len(mitglieder) < 2:
            continue
        # "exakt", wenn irgendein Paar in der Gruppe exakt gleich war, sonst "aehnlich".
        grund = "exakt" if any(
            gruende.get((min(a, b), max(a, b))) == "exakt"
            for idx, a in enumerate(mitglieder) for b in mitglieder[idx + 1:]
        ) else "aehnlich"
        ergebnis.append({"grund": grund, "mitarbeiter": [kandidaten[i] for i in mitglieder]})

    ergebnis.sort(key=lambda g: (g["grund"] != "exakt", _voller_name(g["mitarbeiter"][0])))
    return ergebnis
