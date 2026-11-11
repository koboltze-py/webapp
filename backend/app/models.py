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
