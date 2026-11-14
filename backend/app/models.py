"""SQLAlchemy-Modelle: Krankmeldungen und Änderungsprotokoll (Audit-Log)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Integer, String, Time

from .database import Base


class SickReport(Base):
    __tablename__ = "sick_reports"

    id = Column(Integer, primary_key=True, index=True)
    reported_at = Column(Date, nullable=False)
    employee = Column(String(150), nullable=False)
    sick_from = Column(Date, nullable=False)
    sick_to = Column(Date, nullable=False)
    call_at = Column(Time, nullable=True)
    accepted_by = Column(String(150), nullable=False, default="")
    notes = Column(String(1000), nullable=False, default="")
    careman_done = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Änderungsprotokoll. Einträge bleiben auch nach Löschung einer
    Krankmeldung erhalten (report_id ist bewusst ohne Fremdschlüssel-Zwang)."""

    __tablename__ = "sick_report_audit"

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    report_id = Column(Integer, nullable=True, index=True)
    action = Column(String(10), nullable=False)  # INSERT / UPDATE / DELETE
    actor_role = Column(String(20), nullable=False)  # admin / disposition
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)


class Benutzer(Base):
    """Einzel-Login für Mitarbeitende (nur im lokalen SQLite-Fallback-Modus
    ohne Supabase relevant - bei aktiver Supabase-Anbindung liegt dieselbe
    Tabelle stattdessen in Supabase, siehe Supabase-Sicherung\\sql\\benutzer.sql,
    damit alle PCs dieselben Logins sehen)."""

    __tablename__ = "benutzer"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    anzeigename = Column(String(150), nullable=False, default="")
    rolle = Column(String(20), nullable=False, default="mitarbeiter")  # mitarbeiter/schichtleitung/admin
    aktiv = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Mitarbeiter(Base):
    """Personal-Stammdaten."""

    __tablename__ = "mitarbeiter"

    id = Column(Integer, primary_key=True, index=True)
    vorname = Column(String(100), nullable=False)
    nachname = Column(String(100), nullable=False)
    personalnummer = Column(String(50), nullable=False, default="")
    funktion = Column(String(100), nullable=False, default="")
    email = Column(String(150), nullable=False, default="")
    telefon = Column(String(50), nullable=False, default="")
    aktiv = Column(Boolean, nullable=False, default=True)
    notizen = Column(String(1000), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DienstplanEintrag(Base):
    """Ein Dienstplan-Eintrag (eine Zeile aus einem importierten
    Tagesdienstplan-Excel, siehe dienstplan_parser.py)."""

    __tablename__ = "dienstplan"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(Date, nullable=False, index=True)
    mitarbeiter_name = Column(String(150), nullable=False)
    dienst_kategorie = Column(String(20), nullable=True)
    start_zeit = Column(String(5), nullable=True)  # "HH:MM"
    end_zeit = Column(String(5), nullable=True)
    ist_krank = Column(Boolean, nullable=False, default=False)
    ist_bulmorfahrer = Column(Boolean, nullable=False, default=False)
    notiz = Column(String(500), nullable=False, default="")
    quelle_datei = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Meldung(Base):
    """Allgemeines Mitteilungsboard (unabhängig von Krankmeldungen)."""

    __tablename__ = "meldungen"

    id = Column(Integer, primary_key=True, index=True)
    titel = Column(String(200), nullable=False)
    text = Column(String(4000), nullable=False, default="")
    autor = Column(String(150), nullable=False, default="")
    angeheftet = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
