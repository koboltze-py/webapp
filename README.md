# DRK FKB – Krankmeldungen (Python/FastAPI-Version)

Eigenständige Neufassung der ursprünglichen Supabase/Netlify-Webapp aus
`..\Background`. Design und Bedienung sind bewusst identisch geblieben –
neu ist ein **eigenes Python-Backend (FastAPI)**, das lokal auf diesem PC
läuft und seine Daten in einer eigenen Datenbank speichert (keine
Cloud-Abhängigkeit mehr, kein Supabase-Konto nötig für den laufenden
Betrieb).

## Projektstruktur

```
Webapp mit Fastapi/
├── backend/                  FastAPI-Server + eigene Datenbank
│   ├── app/                  Python-Quellcode (main.py, Routen, Modelle ...)
│   ├── data/                 krankmeldungen.db (SQLite, entsteht automatisch)
│   ├── requirements.txt
│   └── .env                  wird beim ersten Start automatisch erzeugt
├── frontend/
│   └── index.html            Weboberfläche (gleiches Design wie Original)
├── Supabase-Sicherung/        Werkzeug zum Sichern/Exportieren der ALTEN Supabase-Daten
│   ├── backup_gui.py
│   └── config.json
├── Backups/
│   └── Supabase/              Zielordner der Sicherungen (ein Unterordner je Lauf)
├── start_app.bat              Startet Webapp + Backend gemeinsam
├── start_supabase_backup_gui.bat   Startet die Sicherungs-GUI
└── README.md                  diese Datei
```

## 1. Webapp + Backend starten

Doppelklick auf **`start_app.bat`**.

Das Skript:
1. legt beim allerersten Start eine virtuelle Python-Umgebung an
   (siehe Hinweis zum Speicherort weiter unten),
2. installiert automatisch alle benötigten Pakete (FastAPI, Uvicorn,
   SQLAlchemy …),
3. startet den Server unter `http://127.0.0.1:8000`,
4. öffnet die Webapp automatisch im Standardbrowser.

Backend (Datenbank/API) und Webapp (Oberfläche) laufen dabei **in einem
einzigen Prozess** – es muss nichts separat gestartet werden. Das
Konsolenfenster zeigt die Server-Logs; es sollte geöffnet bleiben,
solange die Webapp genutzt wird. Schließen des Fensters (oder STRG+C)
beendet den Server.

### Anmeldedaten (wie zuvor: zwei gemeinsame Rollen-Logins)

| Rolle | Benutzername | Passwort (Standard) |
|---|---|---|
| Disposition | `DRKFKB` | `Disposition` |
| Admin | `ADMIN` | `BitteAendern123` |

Diese Passwörter stehen (automatisch erzeugt) in `backend\.env`.
**Bitte vor dem produktiven Einsatz ändern** und die Datei nicht
weitergeben. Nach dem Ändern muss der Server neu gestartet werden.

### Wichtiger Hinweis zum Speicherort der virtuellen Python-Umgebung

Da dieser Projektordner in einem sehr langen OneDrive-Pfad liegt, scheitert
die Python-Paketinstallation an der Windows-Pfadlängenbegrenzung, wenn man
die virtuelle Umgebung (`.venv`) direkt hier anlegt. Die Start-Skripte legen
sie deshalb bewusst außerhalb von OneDrive ab:

```
%LOCALAPPDATA%\DRKFKB-Krankmeldungen\venv-backend
%LOCALAPPDATA%\DRKFKB-Krankmeldungen\venv-backup-gui
```

Das ist unproblematisch: Dort liegen nur die (jederzeit neu installierbaren)
Programmbibliotheken, **keine** Krankmeldungsdaten. Diese bleiben ausschließlich
in `backend\data\krankmeldungen.db` innerhalb dieses OneDrive-Ordners.

## 2. Daten / Datenbank

Alle Krankmeldungen und das Änderungsprotokoll liegen in einer einzigen
SQLite-Datenbankdatei:

```
backend\data\krankmeldungen.db
```

Diese Datei wird über OneDrive mitgesichert. **Hinweis:** SQLite-Dateien
vertragen sich nicht gut mit gleichzeitigem Zugriff von zwei Geräten
gleichzeitig. Die App sollte daher immer nur auf einem Rechner gleichzeitig
laufen; vor dem Beenden kurz warten, bis OneDrive die Änderung hochgeladen
hat (grünes Häkchen).

## 3. Funktionsumfang (identisch zum Original)

- Krankmeldung erfassen, bearbeiten, löschen
- Übersicht mit Filtern (Heute/Gestern/Monat/Zeitraum/Mitarbeitersuche)
- Rollen **Disposition** (Tagesgeschäft) und **Admin** (zusätzlich
  Careman-Status setzen/umschalten und Änderungsprotokoll einsehen)
- CSV-Export der aktuellen Ansicht sowie des Änderungsprotokolls
- Änderungsprotokoll: jede Anlage/Änderung/Löschung wird mit
  Vorher-/Nachher-Werten gespeichert und bleibt auch nach Löschung
  eines Eintrags erhalten (nur für Admin sichtbar)

## 4. Supabase-Sicherung (GUI-Werkzeug)

Solange die alte Supabase-basierte Webapp noch parallel läuft, kann mit
**`start_supabase_backup_gui.bat`** eine lokale Sicherung ihrer Daten
erstellt werden – unabhängig von dieser neuen FastAPI-App.

Ablauf:
1. Doppelklick auf `start_supabase_backup_gui.bat` öffnet eine kleine
   Desktop-Oberfläche.
2. Rolle wählen (Disposition oder Admin), Passwort eingeben
   (wird nicht gespeichert).
3. „Anmelden & Sicherung jetzt starten“ klicken.
4. Die Tabellen `sick_reports` (Krankmeldungen) und `sick_report_audit`
   (Änderungsprotokoll, falls in Supabase vorhanden) werden geladen und
   unter

   ```
   Backups\Supabase\<Datum_Uhrzeit>\sick_reports.csv
   Backups\Supabase\<Datum_Uhrzeit>\sick_reports.json
   Backups\Supabase\<Datum_Uhrzeit>\sick_report_audit.csv
   Backups\Supabase\<Datum_Uhrzeit>\sick_report_audit.json
   ```

   gespeichert (CSV für Excel, JSON als Rohdatensicherung).
5. Über „Sicherungsordner öffnen“ lässt sich der Ordner direkt im
   Explorer öffnen.

Die Supabase-Projekt-URL und der öffentliche Anon-/Publishable-Key stehen
in `Supabase-Sicherung\config.json` (identisch zu den Werten aus der
alten `config.js`). Das Passwort wird nie gespeichert.

## 5. Datenschutz (unverändert wichtig)

- Krankmeldungen enthalten besonders schützenswerte Gesundheitsdaten.
- Gemeinsame Logins verhindern individuelle Nachvollziehbarkeit beim
  Anlegen/Bearbeiten – das Änderungsprotokoll dokumentiert zumindest
  die Rolle (Admin/Disposition) und den Zeitpunkt jeder Änderung.
- Keine Diagnosen in Bemerkungen erfassen.
- Standardpasswörter vor Produktivbetrieb ändern (`backend\.env`).
- Sicherungsordner (`Backups\Supabase`) und die Datenbankdatei
  (`backend\data\krankmeldungen.db`) nur geschützt ablegen/freigeben.
- Vor Produktivbetrieb mit den Datenschutzverantwortlichen klären:
  Rechtsgrundlage, TOMs, Aufbewahrung und Löschkonzept, Zugangsberechtigung.

## 6. Manuelle Befehle (optional, für Entwickler)

Falls die `.bat`-Dateien nicht verwendet werden sollen:

```powershell
cd backend
py -3 -m venv C:\pfad\ausserhalb\von\onedrive\venv
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m pip install -r requirements.txt
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Die API-Dokumentation (Swagger UI) ist bei laufendem Server erreichbar
unter: `http://127.0.0.1:8000/api/docs`
