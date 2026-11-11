"""Login/Logout per Session-Cookie. Zwei gemeinsame Rollen-Logins wie zuvor:
ADMIN und DRKFKB (Disposition) - kein individuelles Benutzerkonto je
Mitarbeiter.

Ist eine dauerhafte Supabase-Anbindung konfiguriert (settings.supabase_enabled,
siehe config.py), wird das eingegebene Passwort live gegen das jeweilige
Supabase-Konto geprüft - genau wie bei der alten Webseite unter
..\\Background\\index.html. Andernfalls gilt wie bisher das lokale
Passwort aus backend\\.env."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status

from .. import supabase_client as sb
from ..config import settings
from ..schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    username = payload.username.strip().upper()

    if username == settings.admin_username.upper():
        role = "admin"
    elif username == settings.disposition_username.upper():
        role = "disposition"
    else:
        role = None

    if not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")

    if settings.supabase_enabled:
        email = settings.supabase_login_email_admin if role == "admin" else settings.supabase_login_email_disposition
        try:
            tokens = sb.sign_in(email, payload.password)
        except sb.SupabaseError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")
        request.session["supabase_access_token"] = tokens["access_token"]
        request.session["supabase_refresh_token"] = tokens["refresh_token"]
    else:
        expected_password = settings.admin_password if role == "admin" else settings.disposition_password
        if not expected_password or not secrets.compare_digest(payload.password, expected_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzername oder Passwort falsch.")

    request.session["role"] = role
    request.session["username"] = username
    return {"role": role}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    role = request.session.get("role")
    if role not in ("admin", "disposition"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    return {"role": role}
