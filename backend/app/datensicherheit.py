"""Erkennung von OneDrive-Synchronisationskonflikten bei der lokalen
SQLite-Datenbank (siehe database.py: DB_PATH liegt bewusst innerhalb des mit
OneDrive synchronisierten Projektordners, siehe README.md).

Hintergrund: Läuft die App kurz hintereinander auf zwei verschiedenen
Geräten (oder wird der PC vor vollständigem OneDrive-Hochladen heruntergefahren),
kann OneDrive eine "Konfliktkopie" der Datenbankdatei anlegen (z. B.
krankmeldungen-PCNAME.db) - die eigentlich aktive Datei fällt dann auf einen
älteren Stand zurück, ohne dass das offensichtlich wird (genau das wurde als
Ursache für verschwundene Dienstplan-Importe/Krankmeldungen beobachtet).

Diese Datei verschiebt die Datenbank NICHT automatisch (das wäre ein
größerer Eingriff) - sie macht das Problem nur sichtbar: beim Start wird
geprüft, ob neben der aktiven Datenbankdatei weitere *.db-Dateien im
data-Ordner liegen, und falls ja, lautstark gewarnt (Konsole + Logfile +
API-Endpunkt für eine Hinweisleiste im Frontend, siehe routers/system.py)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .database import DATA_DIR, DB_PATH


@dataclass
class Konfliktkopie:
    dateiname: str
    groesse_bytes: int
    geaendert_am: datetime


def finde_konfliktkopien() -> list[Konfliktkopie]:
    """Sucht im data-Ordner nach weiteren *.db-Dateien neben der aktiven
    Datenbank - typischerweise von OneDrive bei Synchronisationskonflikten
    zwischen zwei Geräten angelegt."""
    if not DATA_DIR.exists():
        return []
    gefunden = []
    for pfad in DATA_DIR.glob("*.db"):
        if pfad.resolve() == DB_PATH.resolve():
            continue
        try:
            stat = pfad.stat()
        except OSError:
            continue
        gefunden.append(
            Konfliktkopie(
                dateiname=pfad.name,
                groesse_bytes=stat.st_size,
                geaendert_am=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return sorted(gefunden, key=lambda k: k.geaendert_am, reverse=True)


def warnungen_text(konfliktkopien: list[Konfliktkopie]) -> list[str]:
    aktiv_stat = DB_PATH.stat() if DB_PATH.exists() else None
    aktiv_geaendert = datetime.fromtimestamp(aktiv_stat.st_mtime) if aktiv_stat else None
    texte = []
    for k in konfliktkopien:
        hinweis = (
            f"Mögliche OneDrive-Synchronisationskonflikt-Kopie der Datenbank gefunden: "
            f"'{k.dateiname}' (geändert am {k.geaendert_am.strftime('%d.%m.%Y %H:%M')})."
        )
        if aktiv_geaendert and k.geaendert_am > aktiv_geaendert:
            hinweis += (
                " ACHTUNG: Diese Datei ist NEUER als die aktuell verwendete Datenbank - "
                "möglicherweise fehlen dadurch kürzlich importierte Dienstpläne oder "
                "Krankmeldungen! Bitte vor dem Löschen dieser Datei mit einem/einer "
                "Administrator:in prüfen (siehe README.md, Abschnitt Datensicherheit)."
            )
        texte.append(hinweis)
    return texte
