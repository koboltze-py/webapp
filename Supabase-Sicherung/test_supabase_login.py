"""Einmaliges Testskript: prueft, ob der Login bei Supabase mit den
bestehenden Zugangsdaten funktioniert (wie in der alten Webseite unter
..\Background\index.html). Zeigt NUR an, ob der Login klappt und welche
Rolle zurueckkommt - das Passwort wird nirgendwo gespeichert oder geloggt.

Ausfuehren:
    cd "Supabase-Sicherung"
    <pfad-zum-venv>\python.exe test_supabase_login.py
"""
from __future__ import annotations

import getpass
import json
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    base_url = config["supabase_url"]
    anon_key = config["supabase_anon_key"]

    print("Rolle waehlen:")
    print("  1 = Disposition (", config.get("login_email_disposition"), ")")
    print("  2 = Admin (", config.get("login_email_admin"), ")")
    choice = input("Auswahl (1/2): ").strip()
    if choice == "1":
        email = config["login_email_disposition"]
        role_label = "disposition"
    elif choice == "2":
        email = config["login_email_admin"]
        role_label = "admin"
    else:
        print("Ungueltige Auswahl.")
        return

    password = getpass.getpass("Supabase-Passwort fuer " + email + ": ")

    resp = requests.post(
        base_url + "/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )

    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("msg") or resp.text
        except Exception:
            detail = resp.text
        print("\nLogin fehlgeschlagen (HTTP " + str(resp.status_code) + "): " + str(detail))
        return

    token = resp.json()["access_token"]
    auth_header = "Bearer " + token
    print("\nLogin erfolgreich fuer Rolle '" + role_label + "' (" + email + ").")

    # Versucht, die Rolle ueber die RPC-Funktion zu ermitteln (wie im alten
    # Frontend) - nur zur Info, falls diese Funktion im Projekt existiert.
    rpc_resp = requests.post(
        base_url + "/rest/v1/rpc/app_current_role",
        headers={
            "apikey": anon_key,
            "Authorization": auth_header,
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    if rpc_resp.status_code == 200:
        print("   app_current_role() liefert: " + repr(rpc_resp.json()))
    else:
        print("   (Hinweis: app_current_role() nicht abrufbar, HTTP " + str(rpc_resp.status_code) + ": " + rpc_resp.text[:200] + ")")

    # Testet lesenden Zugriff auf die Krankmeldungen-Tabelle.
    data_resp = requests.get(
        base_url + "/rest/v1/sick_reports",
        params={"select": "id", "limit": "1"},
        headers={"apikey": anon_key, "Authorization": auth_header},
        timeout=30,
    )
    if data_resp.status_code in (200, 206):
        print("   Lesezugriff auf sick_reports: OK (" + str(len(data_resp.json())) + " Zeile(n) im Test-Query).")
    else:
        print("   Lesezugriff auf sick_reports fehlgeschlagen: HTTP " + str(data_resp.status_code) + ": " + data_resp.text[:200])


if __name__ == "__main__":
    main()
