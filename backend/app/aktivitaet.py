"""Benutzer-Aktivitätsprotokoll ("Logfile" je Account, siehe models.py,
BenutzerAktivitaet): hält fest, welcher Login wann an-/abgemeldet war und
welche Aktion (anlegen/bearbeiten/löschen/importieren) er in welchem
Bereich ausgeführt hat.

Ergänzt die bestehenden fachlichen Änderungsprotokolle (sick_report_audit,
dienstplan_audit), die nur Vorher/Nachher-Werte je Datensatz zeigen, aber
nicht pro Benutzerkonto durchsuchbar/zusammengefasst sind.

Schreiben ist bewusst "best effort": ein Fehler hier darf keine eigentliche
Operation verhindern (siehe mitarbeiter_historie.py, gleiches Prinzip)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Request

from . import supabase_client as sb
from .config import settings
from .database import SessionLocal
from .deps import TIER_ROLES
from .models import BenutzerAktivitaet


def record_activity(
    request: Request,
    *,
    aktion: str,
    bereich: str,
    beschreibung: str = "",
    entity_typ: Optional[str] = None,
    entity_id: Optional[Any] = None,
    entity_bezeichnung: str = "",
    details: Optional[dict] = None,
    username: Optional[str] = None,
    rolle: Optional[str] = None,
) -> None:
    """Schreibt einen Logfile-Eintrag für den aktuell angemeldeten Account.
    `username`/`rolle` können explizit übergeben werden (z. B. direkt nach
    einem Login, bevor/während die Session gesetzt wird); sonst werden sie
    aus der Session gelesen."""
    aktiver_username = username if username is not None else request.session.get("username", "")
    aktive_rolle = rolle if rolle is not None else request.session.get("role", "")

    try:
        if settings.supabase_enabled:
            tier = aktive_rolle if aktive_rolle in TIER_ROLES else "admin"
            sb.insert_row(
                sb.BENUTZER_AKTIVITAET_TABLE,
                {
                    "username": aktiver_username,
                    "rolle": aktive_rolle,
                    "aktion": aktion,
                    "bereich": bereich,
                    "entity_typ": entity_typ,
                    "entity_id": str(entity_id) if entity_id is not None else None,
                    "entity_bezeichnung": entity_bezeichnung,
                    "beschreibung": beschreibung,
                    "details": details,
                },
                access_token=sb.get_tier_access_token(tier),
            )
            return
    except sb.SupabaseError as exc:
        print(f"[WARN] Benutzerprotokoll (Supabase) konnte nicht geschrieben werden: {exc}")
        return

    db = SessionLocal()
    try:
        db.add(
            BenutzerAktivitaet(
                username=aktiver_username,
                rolle=aktive_rolle,
                aktion=aktion,
                bereich=bereich,
                entity_typ=entity_typ,
                entity_id=str(entity_id) if entity_id is not None else None,
                entity_bezeichnung=entity_bezeichnung,
                beschreibung=beschreibung,
                details=details,
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - Protokoll ist best effort
        print(f"[WARN] Benutzerprotokoll konnte nicht geschrieben werden: {exc}")
    finally:
        db.close()


def list_activity() -> list[Any]:
    """Chronologisches Logfile (neueste zuerst), nur lokaler SQLite-Modus
    (im Supabase-Modus übernimmt das routers/audit.py direkt)."""
    db = SessionLocal()
    try:
        return (
            db.query(BenutzerAktivitaet)
            .order_by(BenutzerAktivitaet.event_at.desc(), BenutzerAktivitaet.id.desc())
            .all()
        )
    finally:
        db.close()
