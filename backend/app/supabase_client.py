"""Dünner REST-Client für die dauerhafte Datenspeicherung in Supabase.

Wird nur verwendet, wenn SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY in
backend/.env gesetzt sind (siehe config.py / settings.supabase_enabled).

Der Service-Role-Key umgeht Row-Level-Security vollständig (voller
Lese-/Schreibzugriff ohne Login) und darf daher NUR hier, serverseitig,
verwendet werden – niemals im Frontend/Browser.

Tabellen (siehe Supabase-Sicherung/sql/):
- sick_reports        Krankmeldungen (bereits im alten Supabase-Projekt vorhanden)
- sick_report_audit   Änderungsprotokoll (muss einmalig per SQL angelegt werden)
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

import requests

from .config import settings

REPORTS_TABLE = "sick_reports"
AUDIT_TABLE = "sick_report_audit"

_TIMEOUT = 30


class SupabaseError(RuntimeError):
    """Wird ausgelöst, wenn Supabase einen Fehler zurückgibt oder nicht
    erreichbar ist."""


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _url(table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _serialize(data: dict[str, Any]) -> dict[str, Any]:
    """Wandelt date/time/datetime-Werte in JSON-taugliche ISO-Strings um."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (date, datetime, time)):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise SupabaseError(f"Supabase-Fehler ({resp.status_code}): {resp.text[:300]}")


def list_rows(table: str, order: str) -> list[dict[str, Any]]:
    resp = requests.get(
        _url(table),
        params={"select": "*", "order": order},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp)
    return resp.json()


def get_row(table: str, row_id: str) -> Optional[dict[str, Any]]:
    resp = requests.get(
        _url(table),
        params={"select": "*", "id": f"eq.{row_id}"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp)
    rows = resp.json()
    return rows[0] if rows else None


def insert_row(table: str, data: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(
        _url(table),
        json=_serialize(data),
        headers=_headers(prefer="return=representation"),
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp)
    rows = resp.json()
    return rows[0]


def update_row(table: str, row_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    resp = requests.patch(
        _url(table),
        params={"id": f"eq.{row_id}"},
        json=_serialize(data),
        headers=_headers(prefer="return=representation"),
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp)
    rows = resp.json()
    return rows[0] if rows else None


def delete_row(table: str, row_id: str) -> bool:
    resp = requests.delete(
        _url(table),
        params={"id": f"eq.{row_id}"},
        headers=_headers(prefer="return=representation"),
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp)
    return bool(resp.json())
