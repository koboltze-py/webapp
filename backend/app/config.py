"""Zentrale Konfiguration des Backends.

Liest Einstellungen aus einer .env-Datei im backend-Ordner. Existiert die
Datei noch nicht (z. B. beim allerersten Start), wird sie mit einem
zufällig erzeugten SECRET_KEY und Platzhalter-Passwörtern automatisch
angelegt, damit die App sofort startfähig ist. Die Passwörter sollten
danach umgehend angepasst werden (siehe README.md).
"""
from __future__ import annotations

import json
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
        "DISPOSITION_PASSWORD=Disposition\n"
        "# Nur für Einzel-Logins mit aktiver Supabase-Anbindung nötig, siehe\n"
        "# README.md Abschnitt \"Einzel-Logins für Mitarbeitende\":\n"
        "# TIER_SERVICE_PASSWORD_ADMIN=\n"
        "# TIER_SERVICE_PASSWORD_SCHICHTLEITUNG=\n"
        "# TIER_SERVICE_PASSWORD_MITARBEITER=\n",
        encoding="utf-8",
    )

load_dotenv(ENV_PATH)

# Rollenstufen für die neuen Einzel-Logins (Benutzer-Tabelle). Die bisherigen
# zwei geteilten Logins (ADMIN/DRKFKB) bleiben als Legacy-Zugang erhalten,
# siehe routers/auth.py. "admin" entspricht dem bisherigen Admin-Konto,
# "schichtleitung" dem bisherigen Disposition-Konto, "mitarbeiter" ist neu.
TIER_ROLES = ("mitarbeiter", "schichtleitung", "admin")

# Dauerhafte Supabase-Anbindung: verwendet dieselbe Konfigurationsdatei wie
# das Supabase-Sicherungs-Werkzeug (Project URL + oeffentlicher anon-Key,
# beide ohnehin schon in der alten, oeffentlichen Webseite sichtbar - also
# unkritisch). Ein Geheimschluessel ist NICHT noetig: der Zugriff erfolgt wie
# bei der alten Webseite per Login (E-Mail+Passwort) und Row-Level-Security.
SUPABASE_CONFIG_PATH = BASE_DIR.parent / "Supabase-Sicherung" / "config.json"


def _load_supabase_config() -> dict:
    try:
        return json.loads(SUPABASE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


_supabase_config = _load_supabase_config()


class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "")
    admin_username: str = os.getenv("ADMIN_USERNAME", "ADMIN")
    disposition_username: str = os.getenv("DISPOSITION_USERNAME", "DRKFKB")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    disposition_password: str = os.getenv("DISPOSITION_PASSWORD", "")
    session_max_age_seconds: int = 12 * 60 * 60  # 12 Stunden, wie zuvor üblich

    supabase_url: str = _supabase_config.get("supabase_url", "")
    supabase_anon_key: str = _supabase_config.get("supabase_anon_key", "")
    supabase_login_email_admin: str = _supabase_config.get("login_email_admin", "")
    supabase_login_email_disposition: str = _supabase_config.get("login_email_disposition", "")
    # Drittes Konto für die neue Rollenstufe "mitarbeiter" (Einzel-Logins).
    # Muss einmalig in Supabase Auth angelegt werden, siehe README.md.
    supabase_login_email_mitarbeiter: str = _supabase_config.get("login_email_mitarbeiter", "")

    # Feste Zugangsdaten, mit denen das BACKEND selbst (nicht der Mensch im
    # Browser) sich bei Bedarf als eine der drei Rollenstufen bei Supabase
    # anmeldet - nötig, seit einzelne Mitarbeitende ihr eigenes Passwort
    # haben (siehe routers/auth.py + benutzer-Tabelle) und nicht mehr direkt
    # das Passwort des geteilten Supabase-Kontos eintippen. Kein
    # Service-Role-Key, nur normale Supabase-Auth-Konten mit RLS.
    tier_service_password_admin: str = os.getenv("TIER_SERVICE_PASSWORD_ADMIN", "")
    tier_service_password_schichtleitung: str = os.getenv("TIER_SERVICE_PASSWORD_SCHICHTLEITUNG", "")
    tier_service_password_mitarbeiter: str = os.getenv("TIER_SERVICE_PASSWORD_MITARBEITER", "")

    @property
    def supabase_enabled(self) -> bool:
        return bool(
            self.supabase_url
            and self.supabase_anon_key
            and self.supabase_login_email_admin
            and self.supabase_login_email_disposition
        )

    def tier_email(self, tier: str) -> str:
        return {
            "admin": self.supabase_login_email_admin,
            "schichtleitung": self.supabase_login_email_disposition,
            "mitarbeiter": self.supabase_login_email_mitarbeiter,
        }.get(tier, "")

    def tier_service_password(self, tier: str) -> str:
        return {
            "admin": self.tier_service_password_admin,
            "schichtleitung": self.tier_service_password_schichtleitung,
            "mitarbeiter": self.tier_service_password_mitarbeiter,
        }.get(tier, "")

    @property
    def individual_login_enabled(self) -> bool:
        """True, sobald für alle drei Rollenstufen sowohl das Supabase-Konto
        (E-Mail) als auch das zugehörige Service-Passwort hinterlegt sind."""
        return self.supabase_enabled and all(
            self.tier_email(tier) and self.tier_service_password(tier) for tier in TIER_ROLES
        )


settings = Settings()
