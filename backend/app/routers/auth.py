"""Login/Logout per Session-Cookie. Zwei gemeinsame Rollen-Logins wie zuvor
bei Supabase: ADMIN und DRKFKB (Disposition) – kein individuelles
Benutzerkonto je Mitarbeiter."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status

from ..config import settings
from ..schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    username = payload.username.strip().upper()

    if username == settings.admin_username.upper():
        role = "admin"
        expected_password = settings.admin_password
    elif username == settings.disposition_username.upper():
        role = "disposition"
        expected_password = settings.disposition_password
    else:
        expected_password = None
        role = None

    if not role or not expected_password or not secrets.compare_digest(payload.password, expected_password):
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
