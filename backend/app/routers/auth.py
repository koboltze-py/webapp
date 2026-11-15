"""Login/Logout per Session-Cookie.

Zwei Zugangswege, beide aktiv:

1. Legacy-Sammel-Logins ADMIN/DRKFKB (Disposition) - wie bisher, bleiben
   vorerst bestehen. Ist eine dauerhafte Supabase-Anbindung konfiguriert
   (settings.supabase_enabled), wird das eingegebene Passwort live gegen das
   jeweilige Supabase-Konto geprüft, sonst gegen backend\\.env.

2. Neue Einzel-Logins (Benutzertabelle, siehe modules_repository.py):
   Benutzername + eigenes Passwort (bcrypt-Hash). Nach erfolgreicher Prüfung
   meldet sich das Backend selbst mit einem der drei festen
   Rollenstufen-Service-Konten bei Supabase an (siehe supabase_client.py),
   damit dieselben Row-Level-Security-Regeln wie bisher greifen - die
   Mitarbeitenden tippen dafür nie ein Supabase-Passwort ein.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import supabase_client as sb
from ..aktivitaet import record_activity
from ..config import settings
from ..deps import TIER_ROLES
from ..modules_repository import get_benutzer_repository
from ..schemas import (
    LoginRequest,
    LoginResponse,
    PasswortResetRequest,
    PasswortVergessenRequest,
    PasswortVergessenResponse,
)
from ..security import hash_password, normalize_answer, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _legacy_role(username: str) -> str | None:
    username = username.strip().upper()
    if username == settings.admin_username.upper():
        return "admin"
    if username == settings.disposition_username.upper():
        return "disponent"
    return None


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    benutzer_repo=Depends(get_benutzer_repository),
):
    username = payload.username.strip()

    # Weg 1: Legacy-Sammel-Login (reservierte Benutzernamen ADMIN/DRKFKB).
    legacy_role = _legacy_role(username)
    if legacy_role:
        if settings.supabase_enabled:
            email = settings.tier_email(legacy_role) or (
                settings.supabase_login_email_admin if legacy_role == "admin" else settings.supabase_login_email_disposition
            )
            try:
                tokens = sb.sign_in(email, payload.password)
            except sb.SupabaseError:
                record_activity(request, aktion="LOGIN_FEHLGESCHLAGEN", bereich="Anmeldung", username=username, rolle="", beschreibung="Falsches Passwort oder unbekannter Benutzer.")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")
            # Token landet im geteilten Rollenstufen-Zwischenspeicher statt in
            # der Session - so profitieren auch Einzel-Logins derselben
            # Rolle davon, ohne eigenes Service-Passwort zu benötigen.
            sb.seed_tier_token(legacy_role, tokens)
        else:
            expected_password = settings.admin_password if legacy_role == "admin" else settings.disposition_password
            if not expected_password or not secrets.compare_digest(payload.password, expected_password):
                record_activity(request, aktion="LOGIN_FEHLGESCHLAGEN", bereich="Anmeldung", username=username, rolle="", beschreibung="Falsches Passwort oder unbekannter Benutzer.")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")

        request.session["role"] = legacy_role
        request.session["username"] = username.upper()
        record_activity(request, aktion="LOGIN", bereich="Anmeldung", beschreibung="Anmeldung erfolgreich (Sammel-Login).")
        return LoginResponse(role=legacy_role, username=username.upper(), anzeigename=username.upper())

    # Weg 2: Einzel-Login über die Benutzertabelle.
    benutzer = benutzer_repo.get_by_username(username)
    if not benutzer:
        record_activity(request, aktion="LOGIN_FEHLGESCHLAGEN", bereich="Anmeldung", username=username, rolle="", beschreibung="Falsches Passwort oder unbekannter Benutzer.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")

    password_hash = benutzer["password_hash"] if isinstance(benutzer, dict) else benutzer.password_hash
    aktiv = benutzer["aktiv"] if isinstance(benutzer, dict) else benutzer.aktiv
    rolle = benutzer["rolle"] if isinstance(benutzer, dict) else benutzer.rolle
    anzeigename = benutzer["anzeigename"] if isinstance(benutzer, dict) else benutzer.anzeigename

    if not aktiv or not verify_password(payload.password, password_hash) or rolle not in TIER_ROLES:
        record_activity(request, aktion="LOGIN_FEHLGESCHLAGEN", bereich="Anmeldung", username=username, rolle="", beschreibung="Falsches Passwort, inaktiver Account oder unbekannte Rolle.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")

    if settings.supabase_enabled and not settings.individual_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Einzel-Logins sind noch nicht vollständig eingerichtet (Service-Konten fehlen, siehe README.md).",
        )
    if settings.supabase_enabled:
        try:
            sb.get_tier_access_token(rolle)  # meldet die Rollenstufe bei Bedarf an, Token liegt im Zwischenspeicher
        except sb.SupabaseError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    request.session["role"] = rolle
    request.session["username"] = username
    record_activity(request, aktion="LOGIN", bereich="Anmeldung", beschreibung="Anmeldung erfolgreich.")
    return LoginResponse(role=rolle, username=username, anzeigename=anzeigename or username)


@router.post("/logout")
def logout(request: Request):
    record_activity(request, aktion="LOGOUT", bereich="Anmeldung", beschreibung="Abmeldung.")
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    role = request.session.get("role")
    if role not in ("admin", "disposition", *TIER_ROLES):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    normalized = {"disposition": "disponent"}.get(role, role)
    return {"role": normalized, "username": request.session.get("username", "")}


def _normalisiert(text: str) -> str:
    """Groß-/Kleinschreibung und umgebende Leerzeichen spielen bei der
    Sicherheitsantwort keine Rolle (nutzerfreundlicher), siehe unten."""
    return normalize_answer(text)


@router.post("/passwort-vergessen", response_model=PasswortVergessenResponse)
def passwort_vergessen(
    payload: PasswortVergessenRequest,
    benutzer_repo=Depends(get_benutzer_repository),
):
    """Erster Schritt der Selbstbedienungs-Passwort-Reset-Funktion: liefert
    (falls vorhanden) die hinterlegte Sicherheitsfrage des Accounts. Gibt
    bewusst IMMER eine Antwort mit Status 200 zurück (nie 404), damit sich
    nicht erraten lässt, welche Benutzernamen existieren."""
    benutzer = benutzer_repo.get_by_username(payload.username.strip())
    if not benutzer:
        return PasswortVergessenResponse(sicherheitsfrage=None)
    frage = benutzer["sicherheitsfrage"] if isinstance(benutzer, dict) else benutzer.sicherheitsfrage
    return PasswortVergessenResponse(sicherheitsfrage=frage or None)


@router.post("/passwort-reset")
def passwort_reset(
    payload: PasswortResetRequest,
    request: Request,
    benutzer_repo=Depends(get_benutzer_repository),
):
    """Zweiter Schritt: bei korrekter Antwort auf die Sicherheitsfrage wird
    das neue Passwort gesetzt. Ohne hinterlegte Sicherheitsfrage/Antwort ist
    nur der Admin-Reset (PUT /api/benutzer/{id}) möglich."""
    benutzer = benutzer_repo.get_by_username(payload.username.strip())
    if not benutzer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Benutzername oder Antwort falsch.")
    antwort_hash = benutzer["sicherheitsantwort_hash"] if isinstance(benutzer, dict) else benutzer.sicherheitsantwort_hash
    benutzer_id = benutzer["id"] if isinstance(benutzer, dict) else benutzer.id
    username = benutzer["username"] if isinstance(benutzer, dict) else benutzer.username
    if not antwort_hash or not verify_password(_normalisiert(payload.sicherheitsantwort), antwort_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Benutzername oder Antwort falsch.")
    benutzer_repo.update_benutzer(benutzer_id, {"password_hash": hash_password(payload.neues_passwort)})
    record_activity(
        request, aktion="PASSWORT_RESET", bereich="Anmeldung", username=username, rolle="",
        beschreibung="Passwort über Sicherheitsfrage selbst zurückgesetzt.",
    )
    return {"ok": True}
