"""Datenbank-Setup (SQLite-Datei lokal im backend/data-Ordner)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "krankmeldungen.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Spalten, die nach der ursprünglichen Tabellen-Erstellung ergänzt wurden.
# `Base.metadata.create_all()` legt nur FEHLENDE TABELLEN an, ändert aber
# bestehende Tabellen nicht ab - für bereits befüllte SQLite-Dateien (siehe
# backend/data/krankmeldungen.db) braucht es daher diese leichtgewichtige
# Nachrüst-Migration. Format: {Tabelle: [(Spalte, SQL-Typ-Definition), ...]}.
_NACHTRAEGLICHE_SPALTEN: dict[str, list[tuple[str, str]]] = {
    "dienstplan": [
        ("mitarbeiter_id", "INTEGER"),
        ("ausgeschlossen", "BOOLEAN NOT NULL DEFAULT 0"),
        ("geloescht", "BOOLEAN NOT NULL DEFAULT 0"),
        ("manuell_hinzugefuegt", "BOOLEAN NOT NULL DEFAULT 0"),
        ("verspaetung_minuten", "INTEGER NOT NULL DEFAULT 0"),
        ("verspaetung_erfasst_von", "VARCHAR(80) NOT NULL DEFAULT ''"),
        ("verspaetung_erfasst_am", "DATETIME"),
        ("geloescht_am", "DATETIME"),
        ("geloescht_durch", "VARCHAR(80) NOT NULL DEFAULT ''"),
        ("wiederhergestellt_am", "DATETIME"),
        ("wiederhergestellt_durch", "VARCHAR(80) NOT NULL DEFAULT ''"),
        ("hinzugefuegt_durch", "VARCHAR(80) NOT NULL DEFAULT ''"),
    ],
    "benutzer": [
        ("sicherheitsfrage", "VARCHAR(200) NOT NULL DEFAULT ''"),
        ("sicherheitsantwort_hash", "VARCHAR(255)"),
    ],
    "dienstplan_audit": [
        ("datum", "DATE"),
    ],
    "mitarbeiter": [
        ("geloescht", "BOOLEAN NOT NULL DEFAULT 0"),
        ("geloescht_am", "DATETIME"),
        ("geloescht_durch", "VARCHAR(80) NOT NULL DEFAULT ''"),
    ],
}

# Einmalige Datenmigration: in version2.1 wurde das 3-stufige Rollenmodell
# (mitarbeiter/schichtleitung/admin) auf 4 Stufen erweitert
# (mitarbeiter/disponent/schichtleitung/admin, siehe deps.py) - die alte
# Stufe "schichtleitung" entspricht fachlich der neuen Stufe "disponent",
# die neue Stufe "schichtleitung" ist höherwertiger und anfangs ungenutzt.
# Bestehende Benutzerkonten mit rolle='schichtleitung' müssen daher EINMALIG
# auf 'disponent' umbenannt werden, damit sie nicht plötzlich die neuen,
# höheren Rechte der (gleichnamigen) neuen Stufe erhalten. Per
# schema_migrations-Tabelle als "einmalig" markiert, damit ein Admin, der
# danach bewusst jemanden auf die neue Stufe 'schichtleitung' hochstuft,
# nicht bei jedem Neustart wieder zurückgestuft wird.
_MIGRATION_ROLLE_SCHICHTLEITUNG_ZU_DISPONENT = "v2_1_rolle_schichtleitung_zu_disponent"


def run_startup_migrations() -> None:
    """Ergänzt fehlende Spalten in bereits bestehenden SQLite-Tabellen (siehe
    _NACHTRAEGLICHE_SPALTEN) und führt einmalige Datenmigrationen aus. Muss
    NACH Base.metadata.create_all() aufgerufen werden, damit die Tabellen
    selbst schon existieren. Kein No-Op, wenn eine Tabelle noch gar nicht
    existiert (dann hat create_all sie bereits mit allen aktuellen Spalten
    frisch angelegt - und es gibt dort auch keine alten Datensätze zum
    Migrieren)."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(100) PRIMARY KEY, applied_at TEXT)"
        )
        bereits_existierende_tabellen = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        for tabelle, spalten in _NACHTRAEGLICHE_SPALTEN.items():
            vorhandene_spalten = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({tabelle})").fetchall()
            }
            if not vorhandene_spalten:
                continue  # Tabelle existiert (noch) nicht - nichts zu tun.
            for spalte, sql_typ in spalten:
                if spalte not in vorhandene_spalten:
                    connection.exec_driver_sql(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {sql_typ}")

        bereits_migriert = connection.exec_driver_sql(
            "SELECT 1 FROM schema_migrations WHERE name = ?",
            (_MIGRATION_ROLLE_SCHICHTLEITUNG_ZU_DISPONENT,),
        ).fetchone()
        if not bereits_migriert and "benutzer" in bereits_existierende_tabellen:
            connection.exec_driver_sql(
                "UPDATE benutzer SET rolle = 'disponent' WHERE rolle = 'schichtleitung'"
            )
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))",
                (_MIGRATION_ROLLE_SCHICHTLEITUNG_ZU_DISPONENT,),
            )
