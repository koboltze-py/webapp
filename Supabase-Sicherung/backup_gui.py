"""Supabase-Sicherungs-GUI für DRK FKB Krankmeldungen.

Dieses eigenständige Desktop-Tool meldet sich mit den bestehenden
Supabase-Zugangsdaten (wie in der alten Webapp) an und lädt die Tabellen
'sick_reports' (Krankmeldungen) sowie 'sick_report_audit'
(Änderungsprotokoll, falls vorhanden) herunter. Die Daten werden als CSV
(Excel-kompatibel) und als Rohdaten-JSON in einem datierten Unterordner
unter Backups/Supabase gespeichert.

Es wird NUR der öffentliche Anon-/Publishable-Key aus config.json
verwendet (das ist bereits in der Webseite öffentlich sichtbar). Das
Passwort wird niemals gespeichert, sondern nur zur Laufzeit abgefragt und
an Supabase übermittelt.

Start: siehe start_supabase_backup_gui.bat im Projekt-Hauptordner.
"""
from __future__ import annotations

import csv
import io
import json
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import requests

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"

TABLES = [
    ("sick_reports", "Krankmeldungen"),
    ("sick_report_audit", "Änderungsprotokoll"),
]


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def rows_to_csv(rows: list[dict]) -> str:
    """Erzeugt eine Excel-kompatible CSV (Semikolon, UTF-8 BOM), inkl.
    Schutz gegen CSV-Formel-Injektion wie im Original-Frontend."""
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)

    def clean(value):
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        if text[:1] in ("=", "+", "@", "-", "\t", "\r"):
            text = "'" + text
        return text

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([clean(row.get(col)) for col in columns])
    return "\ufeff" + buffer.getvalue()


def fetch_all_rows(base_url: str, anon_key: str, access_token: str, table: str) -> list[dict]:
    """Lädt alle Zeilen einer PostgREST-Tabelle mit Seitenweiser Abfrage
    (analog zum .range()-Paging der ursprünglichen Webapp)."""
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    while True:
        headers_with_range = dict(headers, Range=f"{offset}-{offset + page_size - 1}")
        resp = requests.get(
            f"{base_url}/rest/v1/{table}",
            params={"select": "*", "order": "id.asc"},
            headers=headers_with_range,
            timeout=30,
        )
        if resp.status_code == 404 or (resp.status_code == 400 and "does not exist" in resp.text):
            raise FileNotFoundError(f"Tabelle '{table}' existiert nicht in diesem Supabase-Projekt.")
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def login_supabase(base_url: str, anon_key: str, email: str, password: str) -> str:
    resp = requests.post(
        f"{base_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code != 200:
        detail = resp.json().get("error_description") or resp.json().get("msg") or resp.text
        raise PermissionError(f"Anmeldung bei Supabase fehlgeschlagen: {detail}")
    return resp.json()["access_token"]


class BackupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DRK FKB – Supabase-Sicherung")
        self.geometry("680x560")
        self.resizable(True, True)

        self.config_data = load_config()
        self.backup_root = (HERE / self.config_data.get("backup_root", "../Backups/Supabase")).resolve()
        self.last_backup_dir: Path | None = None

        self._build_widgets()

    # ---- UI -----------------------------------------------------------
    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        header = ttk.Label(
            self,
            text="Sicherung der Supabase-Datenbank (Krankmeldungen + Änderungsprotokoll)",
            font=("Segoe UI", 11, "bold"),
            wraplength=640,
            justify="left",
        )
        header.pack(fill="x", **pad)

        form = ttk.Frame(self)
        form.pack(fill="x", **pad)

        ttk.Label(form, text="Rolle / Login:").grid(row=0, column=0, sticky="w")
        self.role_var = tk.StringVar(value="disposition")
        role_frame = ttk.Frame(form)
        role_frame.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            role_frame, text="Disposition (DRKFKB)", variable=self.role_var,
            value="disposition", command=self._apply_role,
        ).pack(side="left")
        ttk.Radiobutton(
            role_frame, text="Admin", variable=self.role_var,
            value="admin", command=self._apply_role,
        ).pack(side="left", padx=(10, 0))

        ttk.Label(form, text="Supabase Project URL:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.url_var = tk.StringVar(value=self.config_data.get("supabase_url", ""))
        ttk.Entry(form, textvariable=self.url_var, width=52).grid(row=1, column=1, sticky="we", pady=(8, 0))

        ttk.Label(form, text="Login-E-Mail:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.email_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.email_var, width=52).grid(row=2, column=1, sticky="we", pady=(8, 0))

        ttk.Label(form, text="Passwort:").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.password_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.password_var, show="•", width=52).grid(row=3, column=1, sticky="we", pady=(8, 0))

        form.columnconfigure(1, weight=1)
        self._apply_role()

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", **pad)
        self.start_button = ttk.Button(button_frame, text="Anmelden & Sicherung jetzt starten", command=self._start_backup)
        self.start_button.pack(side="left")
        self.open_folder_button = ttk.Button(button_frame, text="Sicherungsordner öffnen", command=self._open_backup_root, state="normal")
        self.open_folder_button.pack(side="left", padx=(10, 0))

        ttk.Label(self, text="Protokoll:").pack(anchor="w", padx=10)
        self.log_widget = scrolledtext.ScrolledText(self, height=18, state="disabled", wrap="word")
        self.log_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=10, pady=(0, 10))

        self._log(f"Sicherungsordner: {self.backup_root}")

    def _apply_role(self):
        if self.role_var.get() == "admin":
            self.email_var.set(self.config_data.get("login_email_admin", ""))
        else:
            self.email_var.set(self.config_data.get("login_email_disposition", ""))

    # ---- Logging --------------------------------------------------------
    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")

        def _write():
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", f"[{timestamp}] {message}\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

        self.after(0, _write)

    def _set_status(self, message: str):
        self.after(0, lambda: self.status_var.set(message))

    # ---- Aktionen -------------------------------------------------------
    def _open_backup_root(self):
        target = self.last_backup_dir or self.backup_root
        target.mkdir(parents=True, exist_ok=True)
        import os

        os.startfile(target)  # noqa: S606 (gewollt: Windows-Explorer öffnen)

    def _start_backup(self):
        base_url = self.url_var.get().strip().rstrip("/")
        anon_key = self.config_data.get("supabase_anon_key", "")
        email = self.email_var.get().strip()
        password = self.password_var.get()

        if not base_url or not anon_key:
            messagebox.showerror("Fehlende Angaben", "Supabase-URL oder Anon-Key fehlen in config.json.")
            return
        if not email or not password:
            messagebox.showerror("Fehlende Angaben", "Bitte E-Mail und Passwort eingeben.")
            return

        self.start_button.configure(state="disabled")
        self._set_status("Sicherung läuft …")
        thread = threading.Thread(target=self._run_backup, args=(base_url, anon_key, email, password), daemon=True)
        thread.start()

    def _run_backup(self, base_url: str, anon_key: str, email: str, password: str):
        try:
            self._log("Melde mich bei Supabase an …")
            token = login_supabase(base_url, anon_key, email, password)
            self._log("Anmeldung erfolgreich.")

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            target_dir = self.backup_root / stamp
            target_dir.mkdir(parents=True, exist_ok=True)

            any_success = False
            for table, label in TABLES:
                try:
                    self._log(f"Lade Tabelle '{table}' ({label}) …")
                    rows = fetch_all_rows(base_url, anon_key, token, table)
                    (target_dir / f"{table}.json").write_text(
                        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    (target_dir / f"{table}.csv").write_text(rows_to_csv(rows), encoding="utf-8")
                    self._log(f"  -> {len(rows)} Datensätze gesichert.")
                    any_success = True
                except FileNotFoundError as e:
                    self._log(f"  -> Übersprungen: {e}")
                except Exception as e:  # noqa: BLE001
                    self._log(f"  -> Fehler bei '{table}': {e}")

            if any_success:
                self.last_backup_dir = target_dir
                self._log(f"Sicherung abgeschlossen: {target_dir}")
                self._set_status(f"Fertig. Gespeichert unter: {target_dir}")
                self.after(0, lambda: messagebox.showinfo("Sicherung abgeschlossen", f"Die Sicherung wurde gespeichert unter:\n{target_dir}"))
            else:
                self._set_status("Sicherung fehlgeschlagen – siehe Protokoll.")
                self.after(0, lambda: messagebox.showerror("Sicherung fehlgeschlagen", "Es konnten keine Tabellen gesichert werden. Siehe Protokoll."))

        except PermissionError as e:
            self._log(str(e))
            self._set_status("Anmeldung fehlgeschlagen.")
            self.after(0, lambda: messagebox.showerror("Anmeldung fehlgeschlagen", str(e)))
        except Exception as e:  # noqa: BLE001
            self._log(f"Unerwarteter Fehler: {e}")
            self._set_status("Fehler – siehe Protokoll.")
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, lambda: self.start_button.configure(state="normal"))
            self.after(0, lambda: self.password_var.set(""))


if __name__ == "__main__":
    app = BackupApp()
    app.mainloop()
