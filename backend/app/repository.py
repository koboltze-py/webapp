"""Repository-Abstraktion für Krankmeldungen + Änderungsprotokoll.

Zwei Implementierungen hinter derselben Schnittstelle:
- SqliteReportsRepository:   bisheriges Verhalten, lokale SQLite-Datenbank
                             über SQLAlchemy (Standard ohne Supabase-Konfiguration).
- SupabaseReportsRepository: Daten liegen dauerhaft in Supabase (Postgres),
                             Zugriff genau wie bei der alten Webseite per
                             Login (E-Mail+Passwort) + anon-Key, Row-Level-
                             Security entscheidet serverseitig (siehe
                             supabase_client.py und routers/auth.py).

Welche Implementierung verwendet wird, entscheidet
`settings.supabase_enabled` (siehe config.py). Die Router
(routers/reports.py, routers/audit.py) kennen nur diese gemeinsame
Schnittstelle und müssen sich um den Speicherort nicht kümmern.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Iterator, Optional, Union

from fastapi import HTTPException, Request, status

from . import supabase_client as sb
from .config import settings
from .database import SessionLocal
from .deps import session_tier
from .models import AuditLog, SickReport

REPORT_FIELDS = (
    "reported_at",
    "employee",
    "sick_from",
    "sick_to",
    "call_at",
    "accepted_by",
    "notes",
    "careman_done",
)


def _validate_dates(sick_from: date, sick_to: date) -> None:
    if sick_to < sick_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="„Krank bis“ darf nicht vor „Krank von“ liegen.",
        )


def _snapshot_dict(data: dict[str, Any]) -> dict[str, Any]:
    """JSON-serialisierbares Abbild einer Krankmeldung aus einem dict
    (Supabase-Zeile oder Request-Payload) für das Änderungsprotokoll."""

    def conv(value: Any) -> Any:
        if isinstance(value, (date, datetime, time)):
            return value.isoformat()
        return value

    return {key: conv(data.get(key)) for key in REPORT_FIELDS}


def _snapshot_orm(report: SickReport) -> dict[str, Any]:
    return {
        "reported_at": report.reported_at.isoformat() if report.reported_at else None,
        "employee": report.employee,
        "sick_from": report.sick_from.isoformat() if report.sick_from else None,
        "sick_to": report.sick_to.isoformat() if report.sick_to else None,
        "call_at": report.call_at.isoformat(timespec="minutes") if report.call_at else None,
        "accepted_by": report.accepted_by,
        "notes": report.notes,
        "careman_done": report.careman_done,
    }


class SqliteReportsRepository:
    """Bisherige Implementierung: lokale SQLite-Datenbank über SQLAlchemy."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _coerce_id(report_id) -> int:
        """Pfadparameter kommt als str (gemeinsame Schnittstelle mit der
        Supabase-Implementierung), die lokale DB nutzt aber Integer-IDs."""
        try:
            return int(report_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

    def _write_audit(self, *, action: str, report_id, old_data, new_data, actor_role: str) -> None:
        entry = AuditLog(
            event_at=datetime.utcnow(),
            report_id=report_id,
            action=action,
            actor_role=actor_role,
            old_data=old_data,
            new_data=new_data,
        )
        self.db.add(entry)
        self.db.commit()

    def list_reports(self) -> list[SickReport]:
        return (
            self.db.query(SickReport)
            .order_by(SickReport.reported_at.desc(), SickReport.created_at.desc())
            .all()
        )

    def create_report(self, data: dict[str, Any], role: str) -> SickReport:
        _validate_dates(data["sick_from"], data["sick_to"])
        if role != "admin":
            data["careman_done"] = False

        report = SickReport(**data)
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        self._write_audit(action="INSERT", report_id=report.id, old_data=None, new_data=_snapshot_orm(report), actor_role=role)
        return report

    def update_report(self, report_id, data: dict[str, Any], role: str) -> SickReport:
        report = self.db.get(SickReport, self._coerce_id(report_id))
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        _validate_dates(data["sick_from"], data["sick_to"])
        old_data = _snapshot_orm(report)

        if role != "admin":
            data["careman_done"] = report.careman_done

        for key, value in data.items():
            setattr(report, key, value)
        report.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(report)

        self._write_audit(action="UPDATE", report_id=report.id, old_data=old_data, new_data=_snapshot_orm(report), actor_role=role)
        return report

    def toggle_careman(self, report_id, careman_done: bool, role: str) -> SickReport:
        report = self.db.get(SickReport, self._coerce_id(report_id))
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        old_data = _snapshot_orm(report)
        report.careman_done = careman_done
        report.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(report)

        self._write_audit(action="UPDATE", report_id=report.id, old_data=old_data, new_data=_snapshot_orm(report), actor_role=role)
        return report

    def delete_report(self, report_id, role: str) -> None:
        report = self.db.get(SickReport, self._coerce_id(report_id))
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        old_data = _snapshot_orm(report)
        self.db.delete(report)
        self.db.commit()

        self._write_audit(action="DELETE", report_id=report.id, old_data=old_data, new_data=None, actor_role=role)

    def list_audit(self) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .order_by(AuditLog.event_at.desc(), AuditLog.id.desc())
            .all()
        )


class SupabaseReportsRepository:
    """Dauerhafte Anbindung: Daten liegen in Supabase (Postgres). Der Zugriff
    läuft über das feste Service-Konto der aktuellen Rollenstufe (admin/
    schichtleitung/mitarbeiter), siehe supabase_client.get_tier_access_token
    und deps.session_tier - Row-Level-Security in Supabase entscheidet
    serverseitig, was je Rolle sichtbar/änderbar ist."""

    def __init__(self, request: Request):
        self.request = request

    def _tier(self) -> str:
        return session_tier(self.request)

    def _call(self, func, *args, **kwargs):
        """Ruft eine supabase_client-Funktion mit dem Zugriffstoken der
        aktuellen Rollenstufe auf; bei abgelaufenem Token wird einmalig
        erneuert und der Aufruf wiederholt."""
        tier = self._tier()
        try:
            return func(*args, access_token=sb.get_tier_access_token(tier), **kwargs)
        except sb.SupabaseAuthExpired:
            return func(*args, access_token=sb.refresh_tier_access_token(tier), **kwargs)

    def _write_audit(self, *, action: str, report_id, old_data, new_data, actor_role: str) -> None:
        try:
            self._call(
                sb.insert_row,
                sb.AUDIT_TABLE,
                {
                    "report_id": report_id,
                    "action": action,
                    "actor_role": actor_role,
                    "old_data": old_data,
                    "new_data": new_data,
                },
            )
        except sb.SupabaseError as exc:
            # Änderungsprotokoll ist "best effort": existiert die Tabelle/
            # Policy in Supabase (noch) nicht, darf das die eigentliche
            # Krankmeldungs-Operation nicht blockieren (siehe
            # Supabase-Sicherung\sql\sick_report_audit.sql).
            print(f"[WARN] Änderungsprotokoll konnte nicht geschrieben werden: {exc}")

    def list_reports(self) -> list[dict[str, Any]]:
        return self._call(sb.list_rows, sb.REPORTS_TABLE, order="reported_at.desc,created_at.desc")

    def create_report(self, data: dict[str, Any], role: str) -> dict[str, Any]:
        _validate_dates(data["sick_from"], data["sick_to"])
        if role != "admin":
            data["careman_done"] = False

        row = self._call(sb.insert_row, sb.REPORTS_TABLE, data)
        self._write_audit(action="INSERT", report_id=row["id"], old_data=None, new_data=_snapshot_dict(row), actor_role=role)
        return row

    def _get_report(self, report_id: str) -> dict[str, Any]:
        row = self._call(sb.get_row, sb.REPORTS_TABLE, report_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")
        return row

    def update_report(self, report_id: str, data: dict[str, Any], role: str) -> dict[str, Any]:
        old_row = self._get_report(report_id)
        _validate_dates(data["sick_from"], data["sick_to"])
        old_data = _snapshot_dict(old_row)

        if role != "admin":
            data["careman_done"] = old_row.get("careman_done", False)
        data["updated_at"] = datetime.utcnow()

        new_row = self._call(sb.update_row, sb.REPORTS_TABLE, report_id, data)
        if not new_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        self._write_audit(action="UPDATE", report_id=report_id, old_data=old_data, new_data=_snapshot_dict(new_row), actor_role=role)
        return new_row

    def toggle_careman(self, report_id: str, careman_done: bool, role: str) -> dict[str, Any]:
        old_row = self._get_report(report_id)
        old_data = _snapshot_dict(old_row)

        new_row = self._call(
            sb.update_row,
            sb.REPORTS_TABLE,
            report_id,
            {"careman_done": careman_done, "updated_at": datetime.utcnow()},
        )
        if not new_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        self._write_audit(action="UPDATE", report_id=report_id, old_data=old_data, new_data=_snapshot_dict(new_row), actor_role=role)
        return new_row

    def delete_report(self, report_id: str, role: str) -> None:
        old_row = self._get_report(report_id)
        old_data = _snapshot_dict(old_row)

        if not self._call(sb.delete_row, sb.REPORTS_TABLE, report_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Krankmeldung nicht gefunden.")

        self._write_audit(action="DELETE", report_id=report_id, old_data=old_data, new_data=None, actor_role=role)

    def list_audit(self) -> list[dict[str, Any]]:
        try:
            return self._call(sb.list_rows, sb.AUDIT_TABLE, order="event_at.desc,id.desc")
        except sb.SupabaseError:
            return []


ReportsRepository = Union[SqliteReportsRepository, SupabaseReportsRepository]


def get_reports_repository(request: Request) -> Iterator[ReportsRepository]:
    """FastAPI-Dependency: liefert je nach Konfiguration die lokale
    SQLite- oder die dauerhafte Supabase-Implementierung."""
    if settings.supabase_enabled:
        yield SupabaseReportsRepository(request)
        return

    db = SessionLocal()
    try:
        yield SqliteReportsRepository(db)
    finally:
        db.close()
