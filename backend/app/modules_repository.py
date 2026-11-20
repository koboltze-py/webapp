"""Repository-Abstraktionen für die neuen Module (Personal-Stammdaten,
Dienstplan, Meldungen) sowie für die Einzel-Login-Benutzertabelle.

Folgt demselben Muster wie repository.py (SickReport): pro Modul eine
SQLite- und eine Supabase-Implementierung hinter derselben Schnittstelle,
ausgewählt über `settings.supabase_enabled`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterator, Optional

from fastapi import HTTPException, Request, status

from . import supabase_client as sb
from .config import settings
from .database import SessionLocal
from .deps import session_tier
from .models import Benutzer, DienstplanEintrag, DienstplanAudit, Meldung, Mitarbeiter


# ============================================================================
# Benutzer (Einzel-Logins)
# ============================================================================


class SqliteBenutzerRepository:
    def __init__(self, db):
        self.db = db

    def get_by_username(self, username: str) -> Optional[Benutzer]:
        return self.db.query(Benutzer).filter(Benutzer.username == username).first()

    def list_benutzer(self) -> list[Benutzer]:
        return self.db.query(Benutzer).order_by(Benutzer.username).all()

    def create_benutzer(self, data: dict[str, Any]) -> Benutzer:
        if self.get_by_username(data["username"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Benutzername bereits vergeben.")
        benutzer = Benutzer(**data)
        self.db.add(benutzer)
        self.db.commit()
        self.db.refresh(benutzer)
        return benutzer

    def update_benutzer(self, benutzer_id, data: dict[str, Any]) -> Benutzer:
        benutzer = self.db.get(Benutzer, int(benutzer_id))
        if not benutzer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden.")
        for key, value in data.items():
            if value is not None:
                setattr(benutzer, key, value)
        benutzer.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(benutzer)
        return benutzer


class SupabaseBenutzerRepository:
    """Zugriff über das feste 'mitarbeiter'-Rollenstufen-Konto (geringste
    Rechte, ausreichend zum Nachschlagen von Logins), siehe config.py."""

    _LOOKUP_TIER = "mitarbeiter"

    def _call(self, func, *args, **kwargs):
        try:
            token = sb.get_tier_access_token(self._LOOKUP_TIER)
            return func(*args, access_token=token, **kwargs)
        except sb.SupabaseAuthExpired:
            token = sb.refresh_tier_access_token(self._LOOKUP_TIER)
            return func(*args, access_token=token, **kwargs)

    def get_by_username(self, username: str) -> Optional[dict[str, Any]]:
        rows = self._call(sb.list_rows, sb.BENUTZER_TABLE, order="username.asc")
        for row in rows:
            if row.get("username") == username:
                return row
        return None

    def list_benutzer(self) -> list[dict[str, Any]]:
        return self._call(sb.list_rows, sb.BENUTZER_TABLE, order="username.asc")

    def create_benutzer(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.get_by_username(data["username"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Benutzername bereits vergeben.")
        return self._call(sb.insert_row, sb.BENUTZER_TABLE, data)

    def update_benutzer(self, benutzer_id, data: dict[str, Any]) -> dict[str, Any]:
        row = self._call(sb.update_row, sb.BENUTZER_TABLE, benutzer_id, {**data, "updated_at": datetime.utcnow()})
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden.")
        return row


def get_benutzer_repository() -> Iterator["SqliteBenutzerRepository | SupabaseBenutzerRepository"]:
    if settings.individual_login_enabled:
        yield SupabaseBenutzerRepository()
    else:
        db = SessionLocal()
        try:
            yield SqliteBenutzerRepository(db)
        finally:
            db.close()


# ============================================================================
# Mitarbeiter (Personal-Stammdaten)
# ============================================================================


class SqliteMitarbeiterRepository:
    def __init__(self, db):
        self.db = db

    def list_mitarbeiter(self, mit_geloeschten: bool = False) -> list[Mitarbeiter]:
        q = self.db.query(Mitarbeiter)
        if not mit_geloeschten:
            q = q.filter(Mitarbeiter.geloescht.is_(False))
        return q.order_by(Mitarbeiter.nachname, Mitarbeiter.vorname).all()

    def create_mitarbeiter(self, data: dict[str, Any]) -> Mitarbeiter:
        m = Mitarbeiter(**data)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def update_mitarbeiter(self, mitarbeiter_id, data: dict[str, Any]) -> Mitarbeiter:
        m = self.db.get(Mitarbeiter, int(mitarbeiter_id))
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        for key, value in data.items():
            setattr(m, key, value)
        m.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(m)
        return m

    def delete_mitarbeiter(self, mitarbeiter_id, actor_username: str = "") -> Mitarbeiter:
        """Weiches Löschen (siehe models.py:Mitarbeiter.geloescht) - der
        Datensatz bleibt erhalten und kann über restore_mitarbeiter
        wiederhergestellt werden."""
        m = self.db.get(Mitarbeiter, int(mitarbeiter_id))
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        m.geloescht = True
        m.geloescht_am = datetime.utcnow()
        m.geloescht_durch = actor_username
        self.db.commit()
        self.db.refresh(m)
        return m

    def restore_mitarbeiter(self, mitarbeiter_id) -> Mitarbeiter:
        m = self.db.get(Mitarbeiter, int(mitarbeiter_id))
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        m.geloescht = False
        m.geloescht_am = None
        m.geloescht_durch = ""
        self.db.commit()
        self.db.refresh(m)
        return m


class _SupabaseRoleRepository:
    """Gemeinsame Basis für Module, deren Supabase-Zugriff über das
    Zugriffstoken der aktuell eingeloggten Rollenstufe läuft (Session)."""

    def __init__(self, request: Request):
        self.request = request

    def _call(self, func, *args, **kwargs):
        tier = session_tier(self.request)
        try:
            return func(*args, access_token=sb.get_tier_access_token(tier), **kwargs)
        except sb.SupabaseAuthExpired:
            return func(*args, access_token=sb.refresh_tier_access_token(tier), **kwargs)


class SupabaseMitarbeiterRepository(_SupabaseRoleRepository):
    def list_mitarbeiter(self, mit_geloeschten: bool = False) -> list[dict[str, Any]]:
        rows = self._call(sb.list_rows, sb.MITARBEITER_TABLE, order="nachname.asc,vorname.asc")
        if not mit_geloeschten:
            rows = [r for r in rows if not r.get("geloescht")]
        return rows

    def create_mitarbeiter(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._call(sb.insert_row, sb.MITARBEITER_TABLE, data)

    def update_mitarbeiter(self, mitarbeiter_id, data: dict[str, Any]) -> dict[str, Any]:
        row = self._call(sb.update_row, sb.MITARBEITER_TABLE, mitarbeiter_id, {**data, "updated_at": datetime.utcnow()})
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        return row

    def delete_mitarbeiter(self, mitarbeiter_id, actor_username: str = "") -> dict[str, Any]:
        row = self._call(
            sb.update_row, sb.MITARBEITER_TABLE, mitarbeiter_id,
            {"geloescht": True, "geloescht_am": datetime.utcnow(), "geloescht_durch": actor_username},
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        return row

    def restore_mitarbeiter(self, mitarbeiter_id) -> dict[str, Any]:
        row = self._call(
            sb.update_row, sb.MITARBEITER_TABLE, mitarbeiter_id,
            {"geloescht": False, "geloescht_am": None, "geloescht_durch": ""},
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden.")
        return row


def get_mitarbeiter_repository(request: Request) -> Iterator["SqliteMitarbeiterRepository | SupabaseMitarbeiterRepository"]:
    if settings.supabase_enabled:
        yield SupabaseMitarbeiterRepository(request)
    else:
        db = SessionLocal()
        try:
            yield SqliteMitarbeiterRepository(db)
        finally:
            db.close()


# ============================================================================
# Dienstplan
# ============================================================================

# Felder, die im Dienstplan-Änderungsprotokoll (DienstplanAudit) als
# old_data/new_data mitgeschrieben werden - gemeinsam fuer SQLite- und
# Supabase-Implementierung, damit beide dieselben Felder liefern.
_DIENSTPLAN_AUDIT_FELDER = (
    "mitarbeiter_name", "mitarbeiter_id", "dienst_kategorie", "start_zeit", "end_zeit", "ist_krank",
    "ist_bulmorfahrer", "ausgeschlossen", "geloescht", "verspaetung_minuten", "verspaetung_erfasst_von", "notiz",
)


def _snapshot_dienstplan_orm(row: DienstplanEintrag) -> dict[str, Any]:
    return {
        "mitarbeiter_name": row.mitarbeiter_name,
        "mitarbeiter_id": row.mitarbeiter_id,
        "dienst_kategorie": row.dienst_kategorie,
        "start_zeit": row.start_zeit,
        "end_zeit": row.end_zeit,
        "ist_krank": row.ist_krank,
        "ist_bulmorfahrer": row.ist_bulmorfahrer,
        "ausgeschlossen": row.ausgeschlossen,
        "geloescht": row.geloescht,
        "verspaetung_minuten": row.verspaetung_minuten,
        "verspaetung_erfasst_von": row.verspaetung_erfasst_von,
        "notiz": row.notiz,
    }


class SqliteDienstplanRepository:
    def __init__(self, db):
        self.db = db

    def list_eintraege(
        self, von: Optional[date] = None, bis: Optional[date] = None, mit_geloeschten: bool = False
    ) -> list[DienstplanEintrag]:
        q = self.db.query(DienstplanEintrag)
        if von:
            q = q.filter(DienstplanEintrag.datum >= von)
        if bis:
            q = q.filter(DienstplanEintrag.datum <= bis)
        if not mit_geloeschten:
            q = q.filter(DienstplanEintrag.geloescht.is_(False))
        return q.order_by(DienstplanEintrag.datum.desc(), DienstplanEintrag.mitarbeiter_name).all()

    def get_eintrag(self, eintrag_id) -> DienstplanEintrag:
        row = self.db.get(DienstplanEintrag, int(eintrag_id))
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienstplan-Eintrag nicht gefunden.")
        return row

    def replace_tag(self, tag: date, eintraege: list[dict[str, Any]], quelle_datei: str) -> list[DienstplanEintrag]:
        """Ersetzt alle Einträge eines Tages durch einen frischen Import
        (ein Tagesdienstplan wird als Ganzes neu eingelesen)."""
        self.db.query(DienstplanEintrag).filter(DienstplanEintrag.datum == tag).delete()
        rows = []
        for e in eintraege:
            row = DienstplanEintrag(datum=tag, quelle_datei=quelle_datei, **e)
            self.db.add(row)
            rows.append(row)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def create_eintrag(self, tag: date, data: dict[str, Any], actor_role: str = "", actor_username: str = "") -> DienstplanEintrag:
        """Manuelles Hinzufügen einer einzelnen Person zu einem bereits
        bestehenden Tagesdienstplan (siehe routers/dienstplan.py:
        create_dienstplan_eintrag) - unabhängig von einem Excel-Import."""
        row = DienstplanEintrag(datum=tag, quelle_datei="", manuell_hinzugefuegt=True, **data)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self.db.add(
            DienstplanAudit(
                dienstplan_id=row.id, datum=row.datum, mitarbeiter_name=row.mitarbeiter_name, action="HINZUGEFÜGT",
                actor_role=actor_role, actor_username=actor_username,
                old_data=None, new_data=_snapshot_dienstplan_orm(row),
            )
        )
        self.db.commit()
        return row

    def update_eintrag(
        self, eintrag_id, data: dict[str, Any], actor_role: str, actor_username: str, aktion: str = "BEARBEITET",
    ) -> DienstplanEintrag:
        row = self.db.get(DienstplanEintrag, int(eintrag_id))
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienstplan-Eintrag nicht gefunden.")
        old_data = _snapshot_dienstplan_orm(row)
        for key, value in data.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        new_data = _snapshot_dienstplan_orm(row)
        self.db.add(
            DienstplanAudit(
                dienstplan_id=row.id, datum=row.datum, mitarbeiter_name=row.mitarbeiter_name, action=aktion,
                actor_role=actor_role, actor_username=actor_username, old_data=old_data, new_data=new_data,
            )
        )
        self.db.commit()
        return row

    def list_audit(self, von: Optional[date] = None, bis: Optional[date] = None) -> list[DienstplanAudit]:
        """`von`/`bis` filtern auf den betroffenen DIENSTPLAN-TAG
        (DienstplanAudit.datum), NICHT auf den Zeitpunkt der Änderung
        (event_at) - damit z. B. "Änderungen für den 10.11." auch dann
        gefunden werden, wenn die Korrektur erst später vorgenommen wurde."""
        q = self.db.query(DienstplanAudit)
        if von:
            q = q.filter(DienstplanAudit.datum >= von)
        if bis:
            q = q.filter(DienstplanAudit.datum <= bis)
        return q.order_by(DienstplanAudit.event_at.desc(), DienstplanAudit.id.desc()).all()

    def get_quelle(self, tag: date) -> dict[str, Any]:
        rows = self.db.query(DienstplanEintrag).filter(DienstplanEintrag.datum == tag).all()
        if not rows:
            return {"datum": tag, "quelle_datei": None, "importiert_am": None, "anzahl_eintraege": 0}
        return {
            "datum": tag,
            "quelle_datei": rows[0].quelle_datei,
            "importiert_am": max(r.created_at for r in rows),
            "anzahl_eintraege": len(rows),
        }


class SupabaseDienstplanRepository(_SupabaseRoleRepository):
    def list_eintraege(
        self, von: Optional[date] = None, bis: Optional[date] = None, mit_geloeschten: bool = False
    ) -> list[dict[str, Any]]:
        rows = self._call(sb.list_rows, sb.DIENSTPLAN_TABLE, order="datum.desc,mitarbeiter_name.asc")
        if von:
            rows = [r for r in rows if r.get("datum") and r["datum"] >= von.isoformat()]
        if bis:
            rows = [r for r in rows if r.get("datum") and r["datum"] <= bis.isoformat()]
        if not mit_geloeschten:
            rows = [r for r in rows if not r.get("geloescht")]
        return rows

    def get_eintrag(self, eintrag_id) -> dict[str, Any]:
        row = self._call(sb.get_row, sb.DIENSTPLAN_TABLE, eintrag_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienstplan-Eintrag nicht gefunden.")
        return row

    def replace_tag(self, tag: date, eintraege: list[dict[str, Any]], quelle_datei: str) -> list[dict[str, Any]]:
        bestehende = self._call(sb.list_rows, sb.DIENSTPLAN_TABLE, order="id.asc")
        for row in bestehende:
            if row.get("datum") == tag.isoformat():
                self._call(sb.delete_row, sb.DIENSTPLAN_TABLE, row["id"])
        neue = []
        for e in eintraege:
            row = self._call(sb.insert_row, sb.DIENSTPLAN_TABLE, {"datum": tag, "quelle_datei": quelle_datei, **e})
            neue.append(row)
        return neue

    def create_eintrag(self, tag: date, data: dict[str, Any], actor_role: str = "", actor_username: str = "") -> dict[str, Any]:
        row = self._call(
            sb.insert_row, sb.DIENSTPLAN_TABLE,
            {"datum": tag, "quelle_datei": "", "manuell_hinzugefuegt": True, **data},
        )
        try:
            self._call(
                sb.insert_row, sb.DIENSTPLAN_AUDIT_TABLE,
                {
                    "dienstplan_id": row.get("id"), "datum": row.get("datum"),
                    "mitarbeiter_name": row.get("mitarbeiter_name", ""),
                    "action": "HINZUGEFÜGT", "actor_role": actor_role, "actor_username": actor_username,
                    "old_data": None,
                    "new_data": {k: row.get(k) for k in _DIENSTPLAN_AUDIT_FELDER},
                },
            )
        except sb.SupabaseError as exc:
            print(f"[WARN] Dienstplan-Änderungsprotokoll konnte nicht geschrieben werden: {exc}")
        return row

    def update_eintrag(
        self, eintrag_id, data: dict[str, Any], actor_role: str, actor_username: str, aktion: str = "BEARBEITET",
    ) -> dict[str, Any]:
        old_row = self._call(sb.get_row, sb.DIENSTPLAN_TABLE, eintrag_id)
        if not old_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienstplan-Eintrag nicht gefunden.")
        new_row = self._call(sb.update_row, sb.DIENSTPLAN_TABLE, eintrag_id, data)
        if not new_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienstplan-Eintrag nicht gefunden.")
        try:
            self._call(
                sb.insert_row,
                sb.DIENSTPLAN_AUDIT_TABLE,
                {
                    "dienstplan_id": eintrag_id,
                    "datum": new_row.get("datum"),
                    "mitarbeiter_name": new_row.get("mitarbeiter_name", ""),
                    "action": aktion,
                    "actor_role": actor_role,
                    "actor_username": actor_username,
                    "old_data": {k: old_row.get(k) for k in _DIENSTPLAN_AUDIT_FELDER},
                    "new_data": {k: new_row.get(k) for k in _DIENSTPLAN_AUDIT_FELDER},
                },
            )
        except sb.SupabaseError as exc:
            print(f"[WARN] Dienstplan-Änderungsprotokoll konnte nicht geschrieben werden: {exc}")
        return new_row

    def list_audit(self, von: Optional[date] = None, bis: Optional[date] = None) -> list[dict[str, Any]]:
        """`von`/`bis` filtern auf den betroffenen Dienstplan-Tag (Spalte
        `datum`), nicht auf event_at, siehe SqliteDienstplanRepository."""
        try:
            rows = self._call(sb.list_rows, sb.DIENSTPLAN_AUDIT_TABLE, order="event_at.desc,id.desc")
        except sb.SupabaseError:
            return []
        if von:
            rows = [r for r in rows if r.get("datum") and r["datum"] >= von.isoformat()]
        if bis:
            rows = [r for r in rows if r.get("datum") and r["datum"] <= bis.isoformat()]
        return rows

    def get_quelle(self, tag: date) -> dict[str, Any]:
        rows = [r for r in self._call(sb.list_rows, sb.DIENSTPLAN_TABLE, order="id.asc") if r.get("datum") == tag.isoformat()]
        if not rows:
            return {"datum": tag, "quelle_datei": None, "importiert_am": None, "anzahl_eintraege": 0}
        return {
            "datum": tag,
            "quelle_datei": rows[0].get("quelle_datei"),
            "importiert_am": max(r.get("created_at") for r in rows),
            "anzahl_eintraege": len(rows),
        }


def get_dienstplan_repository(request: Request) -> Iterator["SqliteDienstplanRepository | SupabaseDienstplanRepository"]:
    if settings.supabase_enabled:
        yield SupabaseDienstplanRepository(request)
    else:
        db = SessionLocal()
        try:
            yield SqliteDienstplanRepository(db)
        finally:
            db.close()


def list_dienstplan_oeffentlich(tag: date) -> list[dict[str, Any]]:
    """Dienstplan eines Tages ohne Login (für die Wandanzeige, siehe
    routers/wandanzeige.py). Nutzt im Supabase-Modus das Mitarbeiter-
    Service-Konto (geringste Rechte); im lokalen Modus direkten DB-Zugriff."""
    if settings.supabase_enabled:
        try:
            token = sb.get_tier_access_token("mitarbeiter")
            rows = sb.list_rows(sb.DIENSTPLAN_TABLE, order="mitarbeiter_name.asc", access_token=token)
        except sb.SupabaseError:
            return []
        return [r for r in rows if r.get("datum") == tag.isoformat()]

    db = SessionLocal()
    try:
        rows = (
            db.query(DienstplanEintrag)
            .filter(DienstplanEintrag.datum == tag)
            .order_by(DienstplanEintrag.mitarbeiter_name)
            .all()
        )
        return [
            {
                "mitarbeiter_name": r.mitarbeiter_name,
                "dienst_kategorie": r.dienst_kategorie,
                "start_zeit": r.start_zeit,
                "end_zeit": r.end_zeit,
                "ist_krank": r.ist_krank,
                "ist_bulmorfahrer": r.ist_bulmorfahrer,
            }
            for r in rows
        ]
    finally:
        db.close()


# ============================================================================
# Meldungen (allgemeines Mitteilungsboard)
# ============================================================================


class SqliteMeldungenRepository:
    def __init__(self, db):
        self.db = db

    def list_meldungen(self) -> list[Meldung]:
        return self.db.query(Meldung).order_by(Meldung.angeheftet.desc(), Meldung.created_at.desc()).all()

    def create_meldung(self, data: dict[str, Any], autor: str) -> Meldung:
        m = Meldung(**data, autor=autor)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def update_meldung(self, meldung_id, data: dict[str, Any]) -> Meldung:
        m = self.db.get(Meldung, int(meldung_id))
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meldung nicht gefunden.")
        for key, value in data.items():
            setattr(m, key, value)
        m.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(m)
        return m

    def delete_meldung(self, meldung_id) -> None:
        m = self.db.get(Meldung, int(meldung_id))
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meldung nicht gefunden.")
        self.db.delete(m)
        self.db.commit()


class SupabaseMeldungenRepository(_SupabaseRoleRepository):
    def list_meldungen(self) -> list[dict[str, Any]]:
        return self._call(sb.list_rows, sb.MELDUNGEN_TABLE, order="angeheftet.desc,created_at.desc")

    def create_meldung(self, data: dict[str, Any], autor: str) -> dict[str, Any]:
        return self._call(sb.insert_row, sb.MELDUNGEN_TABLE, {**data, "autor": autor})

    def update_meldung(self, meldung_id, data: dict[str, Any]) -> dict[str, Any]:
        row = self._call(sb.update_row, sb.MELDUNGEN_TABLE, meldung_id, {**data, "updated_at": datetime.utcnow()})
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meldung nicht gefunden.")
        return row

    def delete_meldung(self, meldung_id) -> None:
        if not self._call(sb.delete_row, sb.MELDUNGEN_TABLE, meldung_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meldung nicht gefunden.")


def get_meldungen_repository(request: Request) -> Iterator["SqliteMeldungenRepository | SupabaseMeldungenRepository"]:
    if settings.supabase_enabled:
        yield SupabaseMeldungenRepository(request)
    else:
        db = SessionLocal()
        try:
            yield SqliteMeldungenRepository(db)
        finally:
            db.close()
