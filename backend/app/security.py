"""Passwort-Hashing für die Einzel-Login-Benutzerkonten.

Nutzt die bcrypt-Bibliothek direkt statt über passlib: passlib 1.7.4 (aktuell
letzte PyPI-Version) ist mit bcrypt >= 4.1 nicht kompatibel (bekannter
Fehler "password cannot be longer than 72 bytes" bereits bei kurzen
Passwörtern, da passlib die bcrypt-Versionserkennung falsch durchführt)."""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except Exception:
        return False
