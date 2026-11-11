"""Hilfsfunktionen für rollenbasierten Zugriff (Session-Cookie)."""
from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_current_role(request: Request) -> str:
    role = request.session.get("role")
    if role not in ("admin", "disposition"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    return role


def require_admin(request: Request) -> str:
    role = get_current_role(request)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Admin verfügbar.")
    return role
