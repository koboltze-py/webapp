"""REST-Client für Supabase - genau wie die alte Webseite unter
..\\Background\\index.html: Login per E-Mail+Passwort über Supabase Auth,
danach Zugriff auf die Tabellen mit dem öffentlichen anon-Key plus dem
persönlichen Zugriffstoken des eingeloggten Nutzers. Row-Level-Security in
Supabase entscheidet serverseitig, was je Rolle sichtbar/änderbar ist -
genau wie es im Browser-Frontend auch der Fall war. Ein Service-Role-Key
wird bewusst NICHT verwendet.
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
    """Allgemeiner Supabase-Fehler (Netzwerk, Validierung, fehlende Rechte)."""


class SupabaseAuthExpired(SupabaseError):
    """Zugriffstoken abgelaufen/ungültig - Aufrufer soll mit dem
    refresh_token erneut anmelden (siehe refresh_session())."""


def sign_in(email: str, password: str) -> dict[str, str]:
    """Meldet sich bei Supabase Auth an (wie supabase.auth.signInWithPassword
    im alten Frontend). Gibt access_token + refresh_token zurück."""
    resp = requests.post(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": settings.supabase_anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SupabaseError("Anmeldung bei Supabase fehlgeschlagen.")
    data = resp.json()
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"]}


def refresh_session(refresh_token: str) -> dict[str, str]:
    """Erneuert ein abgelaufenes Zugriffstoken, ohne erneut Passwort einzugeben."""
    resp = requests.post(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "refresh_token"},
        headers={"apikey": settings.supabase_anon_key, "Content-Type": "application/json"},
        json={"refresh_token": refresh_token},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SupabaseError("Sitzung konnte nicht erneuert werden.")
    data = resp.json()
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"]}


def _headers(access_token: str) -> dict[str, str]:
    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


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


def _check(resp: requests.Response) -> None:
    if resp.status_code == 401:
        raise SupabaseAuthExpired(resp.text[:200])
    if resp.status_code >= 400:
        raise SupabaseError(f"Supabase-Fehler ({resp.status_code}): {resp.text[:300]}")


def list_rows(table: str, order: str, access_token: str) -> list[dict[str, Any]]:
    resp = requests.get(
        _url(table),
        params={"select": "*", "order": order},
        headers=_headers(access_token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    return resp.json()


def get_row(table: str, row_id: str, access_token: str) -> Optional[dict[str, Any]]:
    resp = requests.get(
        _url(table),
        params={"select": "*", "id": f"eq.{row_id}"},
        headers=_headers(access_token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    rows = resp.json()
    return rows[0] if rows else None


def insert_row(table: str, data: dict[str, Any], access_token: str) -> dict[str, Any]:
    headers = _headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.post(_url(table), json=_serialize(data), headers=headers, timeout=_TIMEOUT)
    _check(resp)
    return resp.json()[0]


def update_row(table: str, row_id: str, data: dict[str, Any], access_token: str) -> Optional[dict[str, Any]]:
    headers = _headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.patch(
        _url(table),
        params={"id": f"eq.{row_id}"},
        json=_serialize(data),
        headers=headers,
        timeout=_TIMEOUT,
    )
    _check(resp)
    rows = resp.json()
    return rows[0] if rows else None


def delete_row(table: str, row_id: str, access_token: str) -> bool:
    headers = _headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.delete(
        _url(table),
        params={"id": f"eq.{row_id}"},
        headers=headers,
        timeout=_TIMEOUT,
    )
    _check(resp)
    return bool(resp.json())
