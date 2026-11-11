"""Zentrale Konfiguration des Backends.

Liest Einstellungen aus einer .env-Datei im backend-Ordner. Existiert die
Datei noch nicht (z. B. beim allerersten Start), wird sie mit einem
zufällig erzeugten SECRET_KEY und Platzhalter-Passwörtern automatisch
angelegt, damit die App sofort startfähig ist. Die Passwörter sollten
danach umgehend angepasst werden (siehe README.md).
"""
from __future__ import annotations

import secrets
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    generated_secret = secrets.token_hex(32)
    ENV_PATH.write_text(
        "# Automatisch erzeugt beim ersten Start. Diese Datei NICHT teilen.\n"
        f"SECRET_KEY={generated_secret}\n"
        "ADMIN_USERNAME=ADMIN\n"
        "DISPOSITION_USERNAME=DRKFKB\n"
        "ADMIN_PASSWORD=BitteAendern123\n"
        "DISPOSITION_PASSWORD=Disposition\n",
        encoding="utf-8",
    )

load_dotenv(ENV_PATH)


class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "")
    admin_username: str = os.getenv("ADMIN_USERNAME", "ADMIN")
    disposition_username: str = os.getenv("DISPOSITION_USERNAME", "DRKFKB")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    disposition_password: str = os.getenv("DISPOSITION_PASSWORD", "")
    session_max_age_seconds: int = 12 * 60 * 60  # 12 Stunden, wie zuvor üblich


settings = Settings()
