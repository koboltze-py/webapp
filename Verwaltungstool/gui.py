"""DRK FKB – Verwaltungstool (Desktop-GUI).

Eigenständiges Tkinter-Tool für:
  - Mitarbeiter-Stammdaten anlegen/bearbeiten/löschen
  - Benutzerkonten (Einzel-Logins) anlegen/bearbeiten
  - Tagesdienstpläne aus Excel-Dateien importieren

Spricht dieselbe FastAPI-Webapp an wie der Browser (siehe backend\\app),
über die ganz normale /api/...-Schnittstelle mit Login-Session-Cookie -
keine eigene Datenbank- oder Supabase-Anbindung, keine doppelte
Validierungslogik. Die Webapp muss dafür laufen (siehe start_app.bat).

Start: siehe start_verwaltungstool.bat im Projekt-Hauptordner.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests

DEFAULT_SERVER = "http://127.0.0.1:8000"
ROLLEN = ["mitarbeiter", "schichtleitung", "admin"]
ROLLEN_LABEL = {"mitarbeiter": "Mitarbeiter", "schichtleitung": "Schichtleitung", "admin": "Admin"}


class ApiError(RuntimeError):
    pass


class ApiClient:
    """Dünner Wrapper um requests.Session() für die /api/...-Endpunkte."""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = DEFAULT_SERVER
        self.rolle: str | None = None
        self.username: str | None = None

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def _handle(self, resp: requests.Response):
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ApiError(str(detail))
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def login(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        resp = self.session.post(self._url("/api/auth/login"), json={"username": username, "password": password}, timeout=30)
        data = self._handle(resp)
        self.rolle = data["role"]
        self.username = data.get("username", username)
        return data

    def logout(self):
        try:
            self.session.post(self._url("/api/auth/logout"), timeout=10)
        except Exception:
            pass

    # ---- Mitarbeiter ----------------------------------------------------
    def list_mitarbeiter(self):
        return self._handle(self.session.get(self._url("/api/mitarbeiter"), timeout=30))

    def create_mitarbeiter(self, data: dict):
        return self._handle(self.session.post(self._url("/api/mitarbeiter"), json=data, timeout=30))

    def update_mitarbeiter(self, mid, data: dict):
        return self._handle(self.session.put(self._url(f"/api/mitarbeiter/{mid}"), json=data, timeout=30))

    def delete_mitarbeiter(self, mid):
        return self._handle(self.session.delete(self._url(f"/api/mitarbeiter/{mid}"), timeout=30))

    # ---- Benutzer ---------------------------------------------------------
    def list_benutzer(self):
        return self._handle(self.session.get(self._url("/api/benutzer"), timeout=30))

    def create_benutzer(self, data: dict):
        return self._handle(self.session.post(self._url("/api/benutzer"), json=data, timeout=30))

    def update_benutzer(self, bid, data: dict):
        return self._handle(self.session.put(self._url(f"/api/benutzer/{bid}"), json=data, timeout=30))

    # ---- Dienstplan ---------------------------------------------------------
    def import_dienstplan(self, file_path: Path):
        with open(file_path, "rb") as fh:
            files = {"datei": (file_path.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            resp = self.session.post(self._url("/api/dienstplan/import"), files=files, timeout=60)
        return self._handle(resp)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DRK FKB – Verwaltungstool")
        self.geometry("920x620")
        self.minsize(820, 560)

        self.api = ApiClient()
        self.mitarbeiter_rows: list[dict] = []
        self.benutzer_rows: list[dict] = []
        self.selected_mitarbeiter_id = None
        self.selected_benutzer_id = None

        self._build_login_frame()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def _build_login_frame(self):
        self.login_frame = ttk.Frame(self, padding=24)
        self.login_frame.pack(fill="both", expand=True)

        ttk.Label(self.login_frame, text="DRK FKB – Verwaltungstool", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 16)
        )
        ttk.Label(self.login_frame, text="Nur für Admin-Rolle. Erfordert eine laufende Webapp (start_app.bat).").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 16)
        )

        ttk.Label(self.login_frame, text="Server-Adresse:").grid(row=2, column=0, sticky="w", pady=4)
        self.server_var = tk.StringVar(value=DEFAULT_SERVER)
        ttk.Entry(self.login_frame, textvariable=self.server_var, width=40).grid(row=2, column=1, sticky="we", pady=4)

        ttk.Label(self.login_frame, text="Benutzername:").grid(row=3, column=0, sticky="w", pady=4)
        self.username_var = tk.StringVar(value="ADMIN")
        ttk.Entry(self.login_frame, textvariable=self.username_var, width=40).grid(row=3, column=1, sticky="we", pady=4)

        ttk.Label(self.login_frame, text="Passwort:").grid(row=4, column=0, sticky="w", pady=4)
        self.password_var = tk.StringVar()
        pw_entry = ttk.Entry(self.login_frame, textvariable=self.password_var, show="•", width=40)
        pw_entry.grid(row=4, column=1, sticky="we", pady=4)
        pw_entry.bind("<Return>", lambda e: self._do_login())

        self.login_button = ttk.Button(self.login_frame, text="Anmelden", command=self._do_login)
        self.login_button.grid(row=5, column=0, columnspan=2, pady=(16, 4), sticky="we")

        self.login_message = ttk.Label(self.login_frame, text="", foreground="#a21c24", wraplength=460, justify="left")
        self.login_message.grid(row=6, column=0, columnspan=2, sticky="w")

        self.login_frame.columnconfigure(1, weight=1)

    def _do_login(self):
        server = self.server_var.get().strip() or DEFAULT_SERVER
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.login_message.configure(text="Bitte Benutzername und Passwort eingeben.")
            return
        self.login_button.configure(state="disabled")
        self.login_message.configure(text="Anmeldung läuft …", foreground="#5B6475")

        def work():
            try:
                self.api.login(server, username, password)
                self.after(0, self._on_login_success)
            except ApiError as e:
                self.after(0, lambda: self._on_login_failed(str(e)))
            except requests.RequestException as e:
                self.after(0, lambda: self._on_login_failed(f"Server nicht erreichbar: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _on_login_failed(self, message: str):
        self.login_button.configure(state="normal")
        self.login_message.configure(text=message, foreground="#a21c24")

    def _on_login_success(self):
        if self.api.rolle != "admin":
            self.api.logout()
            self.login_button.configure(state="normal")
            self.login_message.configure(
                text="Dieses Tool ist nur für die Admin-Rolle verfügbar. "
                "Angemeldet war: " + ROLLEN_LABEL.get(self.api.rolle, self.api.rolle or "?"),
                foreground="#a21c24",
            )
            return
        self.login_frame.destroy()
        self._build_main_ui()

    # ------------------------------------------------------------------
    # Hauptoberfläche
    # ------------------------------------------------------------------
    def _build_main_ui(self):
        top = ttk.Frame(self, padding=(12, 8))
        top.pack(fill="x")
        ttk.Label(top, text=f"Angemeldet als {self.api.username} (Admin) · {self.api.base_url}").pack(side="left")
        ttk.Button(top, text="Abmelden", command=self._logout).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._build_mitarbeiter_tab(notebook)
        self._build_benutzer_tab(notebook)
        self._build_dienstplan_tab(notebook)

        self._refresh_mitarbeiter()
        self._refresh_benutzer()

    def _logout(self):
        self.api.logout()
        for child in self.winfo_children():
            child.destroy()
        self.api = ApiClient()
        self._build_login_frame()

    # ---- Tab: Mitarbeiter-Stammdaten --------------------------------------
    def _build_mitarbeiter_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Mitarbeiter-Stammdaten")

        columns = ("vorname", "nachname", "personalnummer", "funktion", "email", "telefon", "aktiv")
        headers = ("Vorname", "Nachname", "Personalnr.", "Funktion", "E-Mail", "Telefon", "Status")
        self.ma_tree = ttk.Treeview(tab, columns=columns, show="headings", height=12, selectmode="browse")
        for col, head in zip(columns, headers):
            self.ma_tree.heading(col, text=head)
            self.ma_tree.column(col, width=110, anchor="w")
        self.ma_tree.pack(fill="both", expand=True, side="top")
        self.ma_tree.bind("<<TreeviewSelect>>", self._on_select_mitarbeiter)

        form = ttk.LabelFrame(tab, text="Mitarbeiter:in anlegen/bearbeiten", padding=10)
        form.pack(fill="x", pady=(10, 0))

        self.ma_vars = {k: tk.StringVar() for k in ("vorname", "nachname", "personalnummer", "funktion", "email", "telefon", "notizen")}
        self.ma_aktiv_var = tk.BooleanVar(value=True)

        fields = [
            ("Vorname*", "vorname"), ("Nachname*", "nachname"), ("Personalnummer", "personalnummer"),
            ("Funktion", "funktion"), ("E-Mail", "email"), ("Telefon", "telefon"),
        ]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 3)
            ttk.Label(form, text=label).grid(row=r * 2, column=c, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.ma_vars[key], width=22).grid(row=r * 2 + 1, column=c, sticky="we", padx=4, pady=(0, 6))

        ttk.Checkbutton(form, text="Aktiv", variable=self.ma_aktiv_var).grid(row=4, column=0, sticky="w", padx=4)
        ttk.Label(form, text="Notizen").grid(row=4, column=1, sticky="w", padx=4)
        ttk.Entry(form, textvariable=self.ma_vars["notizen"], width=40).grid(row=5, column=1, columnspan=2, sticky="we", padx=4)

        btns = ttk.Frame(form)
        btns.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="Neu / Zurücksetzen", command=self._reset_mitarbeiter_form).pack(side="left")
        ttk.Button(btns, text="Speichern", command=self._save_mitarbeiter).pack(side="left", padx=6)
        ttk.Button(btns, text="Löschen", command=self._delete_mitarbeiter).pack(side="left")
        ttk.Button(btns, text="Aktualisieren", command=self._refresh_mitarbeiter).pack(side="left", padx=6)

        for c in range(3):
            form.columnconfigure(c, weight=1)

    def _refresh_mitarbeiter(self):
        def work():
            try:
                rows = self.api.list_mitarbeiter()
                self.after(0, lambda: self._fill_mitarbeiter(rows))
            except (ApiError, requests.RequestException) as e:
                self.after(0, lambda: messagebox.showerror("Fehler", f"Mitarbeiter konnten nicht geladen werden:\n{e}"))

        threading.Thread(target=work, daemon=True).start()

    def _fill_mitarbeiter(self, rows: list[dict]):
        self.mitarbeiter_rows = rows
        self.ma_tree.delete(*self.ma_tree.get_children())
        for row in rows:
            self.ma_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["vorname"], row["nachname"], row.get("personalnummer", ""), row.get("funktion", ""),
                        row.get("email", ""), row.get("telefon", ""), "Aktiv" if row.get("aktiv") else "Inaktiv"),
            )

    def _on_select_mitarbeiter(self, _event=None):
        sel = self.ma_tree.selection()
        if not sel:
            return
        row = next((r for r in self.mitarbeiter_rows if str(r["id"]) == sel[0]), None)
        if not row:
            return
        self.selected_mitarbeiter_id = row["id"]
        for key in ("vorname", "nachname", "personalnummer", "funktion", "email", "telefon", "notizen"):
            self.ma_vars[key].set(row.get(key, "") or "")
        self.ma_aktiv_var.set(bool(row.get("aktiv", True)))

    def _reset_mitarbeiter_form(self):
        self.selected_mitarbeiter_id = None
        for var in self.ma_vars.values():
            var.set("")
        self.ma_aktiv_var.set(True)
        self.ma_tree.selection_remove(*self.ma_tree.selection())

    def _save_mitarbeiter(self):
        data = {k: v.get().strip() for k, v in self.ma_vars.items()}
        if not data["vorname"] or not data["nachname"]:
            messagebox.showwarning("Eingabe fehlt", "Vorname und Nachname sind erforderlich.")
            return
        data["aktiv"] = self.ma_aktiv_var.get()
        mid = self.selected_mitarbeiter_id

        def work():
            try:
                if mid:
                    self.api.update_mitarbeiter(mid, data)
                else:
                    self.api.create_mitarbeiter(data)
                self.after(0, self._reset_mitarbeiter_form)
                self.after(0, self._refresh_mitarbeiter)
            except (ApiError, requests.RequestException) as e:
                self.after(0, lambda: messagebox.showerror("Speichern fehlgeschlagen", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _delete_mitarbeiter(self):
        if not self.selected_mitarbeiter_id:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Zeile in der Liste auswählen.")
            return
        name = f"{self.ma_vars['vorname'].get()} {self.ma_vars['nachname'].get()}"
        if not messagebox.askyesno("Löschen bestätigen", f"Mitarbeiter:in '{name}' wirklich löschen?"):
            return
        mid = self.selected_mitarbeiter_id

        def work():
            try:
                self.api.delete_mitarbeiter(mid)
                self.after(0, self._reset_mitarbeiter_form)
                self.after(0, self._refresh_mitarbeiter)
            except (ApiError, requests.RequestException) as e:
                self.after(0, lambda: messagebox.showerror("Löschen fehlgeschlagen", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---- Tab: Benutzerkonten -----------------------------------------------
    def _build_benutzer_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Benutzerkonten (Einzel-Logins)")

        columns = ("username", "anzeigename", "rolle", "aktiv")
        headers = ("Benutzername", "Anzeigename", "Rolle", "Status")
        self.bu_tree = ttk.Treeview(tab, columns=columns, show="headings", height=12, selectmode="browse")
        for col, head in zip(columns, headers):
            self.bu_tree.heading(col, text=head)
            self.bu_tree.column(col, width=140, anchor="w")
        self.bu_tree.pack(fill="both", expand=True, side="top")
        self.bu_tree.bind("<<TreeviewSelect>>", self._on_select_benutzer)

        form = ttk.LabelFrame(tab, text="Benutzerkonto anlegen/bearbeiten", padding=10)
        form.pack(fill="x", pady=(10, 0))

        ttk.Label(form, text="Benutzername*").grid(row=0, column=0, sticky="w", padx=4)
        self.bu_username_var = tk.StringVar()
        self.bu_username_entry = ttk.Entry(form, textvariable=self.bu_username_var, width=22)
        self.bu_username_entry.grid(row=1, column=0, sticky="we", padx=4, pady=(0, 6))

        ttk.Label(form, text="Anzeigename").grid(row=0, column=1, sticky="w", padx=4)
        self.bu_anzeigename_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.bu_anzeigename_var, width=22).grid(row=1, column=1, sticky="we", padx=4, pady=(0, 6))

        ttk.Label(form, text="Rolle").grid(row=0, column=2, sticky="w", padx=4)
        self.bu_rolle_var = tk.StringVar(value="mitarbeiter")
        rolle_box = ttk.Combobox(form, textvariable=self.bu_rolle_var, values=ROLLEN, state="readonly", width=20)
        rolle_box.grid(row=1, column=2, sticky="we", padx=4, pady=(0, 6))

        ttk.Label(form, text="Passwort (bei Neuanlage Pflicht, sonst nur bei Änderung ausfüllen)").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=4
        )
        self.bu_password_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.bu_password_var, show="•", width=22).grid(row=3, column=0, sticky="we", padx=4, pady=(0, 6))

        self.bu_aktiv_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Aktiv", variable=self.bu_aktiv_var).grid(row=3, column=1, sticky="w", padx=4)

        btns = ttk.Frame(form)
        btns.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="Neu / Zurücksetzen", command=self._reset_benutzer_form).pack(side="left")
        ttk.Button(btns, text="Speichern", command=self._save_benutzer).pack(side="left", padx=6)
        ttk.Button(btns, text="Aktualisieren", command=self._refresh_benutzer).pack(side="left")

        note = ttk.Label(
            form,
            text="Hinweis: Konten werden nicht gelöscht, sondern über 'Aktiv' deaktiviert "
            "(Login dann nicht mehr möglich, Historie bleibt nachvollziehbar).",
            foreground="#5B6475", wraplength=640, justify="left",
        )
        note.grid(row=5, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 0))

        for c in range(3):
            form.columnconfigure(c, weight=1)

    def _refresh_benutzer(self):
        def work():
            try:
                rows = self.api.list_benutzer()
                self.after(0, lambda: self._fill_benutzer(rows))
            except (ApiError, requests.RequestException) as e:
                self.after(0, lambda: messagebox.showerror("Fehler", f"Benutzerkonten konnten nicht geladen werden:\n{e}"))

        threading.Thread(target=work, daemon=True).start()

    def _fill_benutzer(self, rows: list[dict]):
        self.benutzer_rows = rows
        self.bu_tree.delete(*self.bu_tree.get_children())
        for row in rows:
            self.bu_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["username"], row.get("anzeigename", ""), ROLLEN_LABEL.get(row["rolle"], row["rolle"]),
                        "Aktiv" if row.get("aktiv") else "Inaktiv"),
            )

    def _on_select_benutzer(self, _event=None):
        sel = self.bu_tree.selection()
        if not sel:
            return
        row = next((r for r in self.benutzer_rows if str(r["id"]) == sel[0]), None)
        if not row:
            return
        self.selected_benutzer_id = row["id"]
        self.bu_username_var.set(row["username"])
        self.bu_username_entry.configure(state="readonly")  # Benutzername nachträglich nicht änderbar
        self.bu_anzeigename_var.set(row.get("anzeigename", "") or "")
        self.bu_rolle_var.set(row.get("rolle", "mitarbeiter"))
        self.bu_aktiv_var.set(bool(row.get("aktiv", True)))
        self.bu_password_var.set("")

    def _reset_benutzer_form(self):
        self.selected_benutzer_id = None
        self.bu_username_entry.configure(state="normal")
        self.bu_username_var.set("")
        self.bu_anzeigename_var.set("")
        self.bu_rolle_var.set("mitarbeiter")
        self.bu_aktiv_var.set(True)
        self.bu_password_var.set("")
        self.bu_tree.selection_remove(*self.bu_tree.selection())

    def _save_benutzer(self):
        username = self.bu_username_var.get().strip()
        password = self.bu_password_var.get()
        if not username:
            messagebox.showwarning("Eingabe fehlt", "Benutzername ist erforderlich.")
            return
        bid = self.selected_benutzer_id

        if not bid:
            if not password or len(password) < 6:
                messagebox.showwarning("Eingabe fehlt", "Für ein neues Konto ist ein Passwort mit mind. 6 Zeichen erforderlich.")
                return
            data = {
                "username": username, "password": password,
                "anzeigename": self.bu_anzeigename_var.get().strip(),
                "rolle": self.bu_rolle_var.get(), "aktiv": self.bu_aktiv_var.get(),
            }

            def work():
                try:
                    self.api.create_benutzer(data)
                    self.after(0, self._reset_benutzer_form)
                    self.after(0, self._refresh_benutzer)
                except (ApiError, requests.RequestException) as e:
                    self.after(0, lambda: messagebox.showerror("Speichern fehlgeschlagen", str(e)))
        else:
            data = {"anzeigename": self.bu_anzeigename_var.get().strip(), "rolle": self.bu_rolle_var.get(), "aktiv": self.bu_aktiv_var.get()}
            if password:
                if len(password) < 6:
                    messagebox.showwarning("Eingabe fehlt", "Neues Passwort muss mind. 6 Zeichen haben.")
                    return
                data["password"] = password

            def work():
                try:
                    self.api.update_benutzer(bid, data)
                    self.after(0, self._reset_benutzer_form)
                    self.after(0, self._refresh_benutzer)
                except (ApiError, requests.RequestException) as e:
                    self.after(0, lambda: messagebox.showerror("Speichern fehlgeschlagen", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---- Tab: Dienstplan-Import --------------------------------------------
    def _build_dienstplan_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Dienstplan-Import")

        ttk.Label(
            tab,
            text="Tagesdienstplan (.xlsx) mit Spalten NAME/DIENST/BEGINN/ENDE importieren.\n"
            "\"KRANK\"/\"K\" wird als Krankmeldung erkannt, gelb hinterlegte Zeilen als Bulli-Fahrer:in.\n"
            "Ein erneuter Import für denselben Tag ersetzt die zuvor importierten Einträge dieses Tages.",
            justify="left", wraplength=800,
        ).pack(anchor="w", pady=(0, 12))

        file_frame = ttk.Frame(tab)
        file_frame.pack(fill="x")
        self.dp_file_var = tk.StringVar(value="Keine Datei ausgewählt.")
        ttk.Entry(file_frame, textvariable=self.dp_file_var, state="readonly", width=70).pack(side="left", fill="x", expand=True)
        ttk.Button(file_frame, text="Datei auswählen …", command=self._choose_dienstplan_file).pack(side="left", padx=(8, 0))

        self.dp_import_button = ttk.Button(tab, text="Importieren", command=self._import_dienstplan, state="disabled")
        self.dp_import_button.pack(anchor="w", pady=(10, 10))

        ttk.Label(tab, text="Ergebnis:").pack(anchor="w")
        self.dp_log = scrolledtext.ScrolledText(tab, height=16, state="disabled", wrap="word")
        self.dp_log.pack(fill="both", expand=True)

        self._dp_selected_file: Path | None = None

    def _log_dienstplan(self, message: str):
        self.dp_log.configure(state="normal")
        self.dp_log.insert("end", message + "\n")
        self.dp_log.see("end")
        self.dp_log.configure(state="disabled")

    def _choose_dienstplan_file(self):
        path = filedialog.askopenfilename(title="Tagesdienstplan auswählen", filetypes=[("Excel-Dateien", "*.xlsx *.xlsm")])
        if not path:
            return
        self._dp_selected_file = Path(path)
        self.dp_file_var.set(str(self._dp_selected_file))
        self.dp_import_button.configure(state="normal")

    def _import_dienstplan(self):
        if not self._dp_selected_file:
            return
        self.dp_import_button.configure(state="disabled")
        self._log_dienstplan(f"Importiere {self._dp_selected_file.name} …")
        file_path = self._dp_selected_file

        def work():
            try:
                result = self.api.import_dienstplan(file_path)
                self.after(0, lambda: self._on_import_done(result))
            except (ApiError, requests.RequestException) as e:
                self.after(0, lambda: self._on_import_failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _on_import_done(self, result: dict):
        self.dp_import_button.configure(state="normal")
        if not result.get("success"):
            self._log_dienstplan(f"FEHLGESCHLAGEN: {result.get('error')}")
            messagebox.showerror("Import fehlgeschlagen", str(result.get("error")))
            return
        self._log_dienstplan(
            f"Erfolgreich importiert für {result.get('datum')}: {result['anzahl_eintraege']} Einträge "
            f"({result['anzahl_krank']} krank, {result['anzahl_bulmorfahrer']} Bulli-Fahrer:in)."
        )
        if result.get("unbekannte_dienste"):
            self._log_dienstplan("Unbekannte Dienstkürzel (bitte prüfen): " + ", ".join(result["unbekannte_dienste"]))
        messagebox.showinfo("Import abgeschlossen", f"{result['anzahl_eintraege']} Einträge importiert.")

    def _on_import_failed(self, message: str):
        self.dp_import_button.configure(state="normal")
        self._log_dienstplan(f"FEHLER: {message}")
        messagebox.showerror("Import fehlgeschlagen", message)


if __name__ == "__main__":
    App().mainloop()
