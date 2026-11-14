"""Hilfsfunktionen für rollenbasierten Zugriff (Session-Cookie).

Rollenstufen seit den Einzel-Logins (siehe routers/auth.py):
  "mitarbeiter"     - einfache Sicht (eigene Module)
  "schichtleitung"  - alle operativen Module (entspricht der bisherigen
                      "disposition"-Rolle)
  "admin"           - zusätzlich Einstellungen/Benutzerverwaltung

Die beiden alten Rollennamen "admin"/"disposition" werden weiterhin
akzeptiert (Legacy-Login bleibt vorerst bestehen) und sind intern identisch
zu "admin"/"schichtleitung"."""
from __future__ import annotations

from fastapi import HTTPException, Request, status

TIER_ROLES = ("mitarbeiter", "schichtleitung", "admin")

# Rangfolge für "mindestens Rolle X" Prüfungen.
_RANG = {"mitarbeiter": 0, "schichtleitung": 1, "admin": 2}

# Legacy-Rollennamen (vor den Einzel-Logins) auf die neuen Stufen abbilden.
_LEGACY_ALIAS = {"disposition": "schichtleitung"}


def _normalize_role(role: str | None) -> str | None:
    if role is None:
        return None
    return _LEGACY_ALIAS.get(role, role)


def session_tier(request: Request) -> str:
    """Rollenstufe (mitarbeiter/schichtleitung/admin) der aktuellen Sitzung,
    normalisiert von Legacy-Rollennamen. Für Repository-Klassen, die darüber
    das passende Supabase-Service-Konto wählen (siehe supabase_client.py)."""
    role = _normalize_role(request.session.get("role"))
    if role not in TIER_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    return role


def get_current_role(request: Request) -> str:
    role = _normalize_role(request.session.get("role"))
    if role not in TIER_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    return role


def require_admin(request: Request) -> str:
    role = get_current_role(request)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Admin verfügbar.")
    return role


def require_schichtleitung(request: Request) -> str:
    """Mindestens Schichtleitung (also auch Admin)."""
    role = get_current_role(request)
    if _RANG[role] < _RANG["schichtleitung"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Schichtleitung/Admin verfügbar.")
    return role
