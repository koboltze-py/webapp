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
BENUTZER_TABLE = "benutzer"
MITARBEITER_TABLE = "mitarbeiter"
DIENSTPLAN_TABLE = "dienstplan"
DIENSTPLAN_AUDIT_TABLE = "dienstplan_audit"
MELDUNGEN_TABLE = "meldungen"

_TIMEOUT = 30

# Zwischengespeicherte Zugriffstoken der drei festen Rollenstufen-Konten
# (admin/schichtleitung/mitarbeiter). Diese Konten gehören dem Backend selbst
# (Zugangsdaten in .env, siehe config.py) - einzelne Mitarbeitende melden sich
# mit ihrem eigenen Login an (benutzer-Tabelle), nicht mit diesen Konten.
_tier_tokens: dict[str, dict[str, str]] = {}


def get_tier_access_token(tier: str) -> str:
    """Liefert ein gültiges Zugriffstoken für das Service-Konto einer
    Rollenstufe, meldet bei Bedarf neu an."""
    cached = _tier_tokens.get(tier)
    if cached:
        return cached["access_token"]
    return _sign_in_tier(tier)["access_token"]


def refresh_tier_access_token(tier: str) -> str:
    """Erneuert das Zugriffstoken einer Rollenstufe (nach Ablauf)."""
    cached = _tier_tokens.get(tier)
    if cached and cached.get("refresh_token"):
        try:
            tokens = refresh_session(cached["refresh_token"])
            _tier_tokens[tier] = tokens
            return tokens["access_token"]
        except SupabaseError:
            pass
    return _sign_in_tier(tier)["access_token"]


def _sign_in_tier(tier: str) -> dict[str, str]:
    email = settings.tier_email(tier)
    password = settings.tier_service_password(tier)
    if not email or not password:
        raise SupabaseError(f"Service-Konto für Rollenstufe '{tier}' ist nicht konfiguriert.")
    tokens = sign_in(email, password)
    _tier_tokens[tier] = tokens
    return tokens


def seed_tier_token(tier: str, tokens: dict[str, str]) -> None:
    """Übernimmt ein frisch erhaltenes Zugriffstoken (z. B. aus dem
    Legacy-Login mit menschlich eingetipptem Passwort) in den
    Rollenstufen-Zwischenspeicher, damit andere Anfragen derselben Rolle es
    mitbenutzen können, ohne ein eigenes Service-Passwort zu benötigen."""
    _tier_tokens[tier] = tokens


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
