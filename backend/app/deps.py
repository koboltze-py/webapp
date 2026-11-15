"""Hilfsfunktionen für rollenbasierten Zugriff (Session-Cookie).

Rollenstufen (seit version2.1, 4 Stufen statt vormals 3):
  "mitarbeiter"     - einfache Sicht (eigene Module)
  "disponent"       - operative Module (Krankmeldungen anlegen/bearbeiten,
                      Mitarbeiter-Stammdaten anlegen/bearbeiten/ausschließen,
                      Dienstplan importieren/exportieren/bearbeiten). KEIN
                      Zugriff auf Mitarbeiter-Verlauf, Benutzerverwaltung
                      oder Änderungsprotokolle. Entspricht der bisherigen
                      (vor version2.1) Rolle "schichtleitung"/der
                      Sammel-Login-Rolle "disposition".
  "schichtleitung"  - alles, was Admin auch kann, AUSSER den Careman-Status
                      zu setzen/umzuschalten (siehe routers/reports.py).
                      Neu seit version2.1, nur über Einzel-Logins vergebbar.
  "admin"           - uneingeschränkter Zugriff (inkl. Careman-Status)

Die alten Rollennamen "admin"/"disposition" werden weiterhin akzeptiert
(Legacy-Sammel-Login bleibt bestehen): "disposition" ist intern identisch zu
"disponent" (siehe routers/auth.py)."""
from __future__ import annotations

from fastapi import HTTPException, Request, status

TIER_ROLES = ("mitarbeiter", "disponent", "schichtleitung", "admin")

# Rangfolge für "mindestens Rolle X" Prüfungen.
_RANG = {"mitarbeiter": 0, "disponent": 1, "schichtleitung": 2, "admin": 3}

# Legacy-Rollennamen (vor den Einzel-Logins, bzw. vor dem 4-Stufen-Modell aus
# version2.1) auf die aktuellen Stufen abbilden.
_LEGACY_ALIAS = {"disposition": "disponent"}


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


def require_disponent(request: Request) -> str:
    """Mindestens Disponent (also auch Schichtleitung/Admin) - die operativen
    Module (Krankmeldungen, Mitarbeiter-Stammdaten, Dienstplan)."""
    role = get_current_role(request)
    if _RANG[role] < _RANG["disponent"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Disponent/Schichtleitung/Admin verfügbar.")
    return role


def require_schichtleitung(request: Request) -> str:
    """Mindestens Schichtleitung (also auch Admin) - alles außer Careman-Status
    (siehe routers/reports.py:toggle_careman) und ausdrücklich Admin-only
    markierte Funktionen."""
    role = get_current_role(request)
    if _RANG[role] < _RANG["schichtleitung"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Schichtleitung/Admin verfügbar.")
    return role
