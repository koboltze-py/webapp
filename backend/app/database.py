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
    "dienstplan": [("mitarbeiter_id", "INTEGER"), ("ausgeschlossen", "BOOLEAN NOT NULL DEFAULT 0")],
}


def run_startup_migrations() -> None:
    """Ergänzt fehlende Spalten in bereits bestehenden SQLite-Tabellen (siehe
    _NACHTRAEGLICHE_SPALTEN). Muss NACH Base.metadata.create_all() aufgerufen
    werden, damit die Tabellen selbst schon existieren. Kein No-Op, wenn eine
    Tabelle noch gar nicht existiert (dann hat create_all sie bereits mit
    allen aktuellen Spalten frisch angelegt)."""
    with engine.begin() as connection:
        for tabelle, spalten in _NACHTRAEGLICHE_SPALTEN.items():
            vorhandene_spalten = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({tabelle})").fetchall()
            }
            if not vorhandene_spalten:
                continue  # Tabelle existiert (noch) nicht - nichts zu tun.
            for spalte, sql_typ in spalten:
                if spalte not in vorhandene_spalten:
                    connection.exec_driver_sql(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {sql_typ}")
