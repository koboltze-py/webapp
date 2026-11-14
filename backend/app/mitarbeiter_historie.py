"""Mitarbeiter-Historie: Ereignis-Log je Mitarbeiter:in (siehe models.py,
MitarbeiterEreignis). Hält fest, wie oft/wann jemand krank gemeldet wurde,
wann eine laufende Krankmeldung storniert wurde und wann sich die
Stammdaten geändert haben - unabhängig davon, ob die eigentlichen Fachdaten
gerade in der lokalen SQLite-Datenbank oder in Supabase liegen.

Das Schreiben ist bewusst "best effort" (wie das bestehende
Änderungsprotokoll in repository.py): ein Fehler hier darf die eigentliche
Operation (Krankmeldung anlegen, Mitarbeiter speichern, ...) nie verhindern.
"""
from __future__ import annotations

from typing import Any, Optional

from . import supabase_client as sb
from .config import settings
from .database import SessionLocal
from .deps import TIER_ROLES
from .models import MitarbeiterEreignis


def record_ereignis(
    *,
    mitarbeiter_id: Optional[int],
    mitarbeiter_name: str,
    ereignis_typ: str,
    beschreibung: str = "",
    bezug_typ: Optional[str] = None,
    bezug_id: Optional[Any] = None,
    actor_username: str = "",
    actor_role: str = "",
    details: Optional[dict] = None,
) -> None:
    """Schreibt einen Historie-Eintrag für einen Mitarbeiter. Ohne bekannte
    mitarbeiter_id (Name konnte nicht zugeordnet werden) wird trotzdem
    protokolliert - nur eben ohne Verknüpfung zum Stammdatensatz, damit der
    Vorgang selbst nicht verloren geht."""
    try:
        if settings.supabase_enabled:
            tier = actor_role if actor_role in TIER_ROLES else "admin"
            sb.insert_row(
                sb.MITARBEITER_EREIGNIS_TABLE,
                {
                    "mitarbeiter_id": mitarbeiter_id,
                    "mitarbeiter_name": mitarbeiter_name,
                    "ereignis_typ": ereignis_typ,
                    "beschreibung": beschreibung,
                    "bezug_typ": bezug_typ,
                    "bezug_id": str(bezug_id) if bezug_id is not None else None,
                    "actor_username": actor_username,
                    "actor_role": actor_role,
                    "details": details,
                },
                access_token=sb.get_tier_access_token(tier),
            )
            return
    except sb.SupabaseError as exc:
        print(f"[WARN] Mitarbeiter-Historie (Supabase) konnte nicht geschrieben werden: {exc}")
        return

    db = SessionLocal()
    try:
        db.add(
            MitarbeiterEreignis(
                mitarbeiter_id=mitarbeiter_id,
                mitarbeiter_name=mitarbeiter_name,
                ereignis_typ=ereignis_typ,
                beschreibung=beschreibung,
                bezug_typ=bezug_typ,
                bezug_id=str(bezug_id) if bezug_id is not None else None,
                actor_username=actor_username,
                actor_role=actor_role,
                details=details,
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - Historie ist best effort
        print(f"[WARN] Mitarbeiter-Historie konnte nicht geschrieben werden: {exc}")
    finally:
        db.close()


def list_ereignisse(mitarbeiter_id: int) -> list[Any]:
    """Chronologische Historie (neueste zuerst) eines Mitarbeiters - nur für
    den lokalen SQLite-Modus (im Supabase-Modus übernimmt das die jeweilige
    Repository-Schicht, siehe routers/mitarbeiter.py)."""
    db = SessionLocal()
    try:
        return (
            db.query(MitarbeiterEreignis)
            .filter(MitarbeiterEreignis.mitarbeiter_id == mitarbeiter_id)
            .order_by(MitarbeiterEreignis.event_at.desc(), MitarbeiterEreignis.id.desc())
            .all()
        )
    finally:
        db.close()


def list_alle_ereignisse() -> list[Any]:
    """Komplette Mitarbeiter-Historie über ALLE Mitarbeitenden (neueste
    zuerst) - Grundlage für den Excel-Export im Verwaltungstool (siehe
    routers/mitarbeiter.py:/api/mitarbeiter/historie/export)."""
    db = SessionLocal()
    try:
        return (
            db.query(MitarbeiterEreignis)
            .order_by(MitarbeiterEreignis.event_at.desc(), MitarbeiterEreignis.id.desc())
            .all()
        )
    finally:
        db.close()
