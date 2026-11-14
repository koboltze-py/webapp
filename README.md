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
├── Verwaltungstool/            Desktop-GUI fuer Mitarbeiter/Benutzer/Dienstplan-Import
│   ├── gui.py
│   └── requirements.txt
├── start_app.bat              Startet Webapp + Backend gemeinsam
├── start_supabase_backup_gui.bat   Startet die Sicherungs-GUI
├── start_verwaltungstool.bat   Startet das Verwaltungstool
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

### Datenhaltung: lokal oder Supabase

**Standardmäßig läuft die App vollständig lokal** (SQLite-Datei
`backend\data\krankmeldungen.db`) - für **alle** Module (Krankmeldungen,
Mitarbeiter-Stammdaten, Dienstplan, Meldungen, Benutzerkonten), auch wenn
`Supabase-Sicherung\config.json` bereits gültige Zugangsdaten enthält.
Gesteuert wird das über den Schalter `SUPABASE_AKTIV` in `backend\.env`
(Standard: `false`) - am einfachsten über das **Verwaltungstool**, Reiter
„Datenhaltung" umschaltbar (schreibt dieselbe `.env`-Datei). Nach einer
Umschaltung muss die Webapp (`start_app.bat`) neu gestartet werden, damit
sie wirksam wird.

Dort lässt sich auch **einmalig** der aktuelle Stand aus Supabase
(Krankmeldungen + Änderungsprotokoll, falls vorhanden) in die lokale
Datenbank übernehmen (Rolle + Supabase-Passwort eingeben, „Jetzt einmalig
importieren"). Das ist als einmaliger Umzug gedacht, keine laufende
Synchronisation - ein erneuter Lauf hängt die Daten erneut an, ohne auf
Duplikate zu prüfen.

Langfristig ist eine **dauerhafte** Supabase-Anbindung vorgesehen (siehe
unten), damit mehrere PCs dieselben Daten sehen - bis diese vollständig
eingerichtet ist (neues Mitarbeiter-Servicekonto, SQL-Migrationen,
Service-Passwörter, siehe weiter unten), bleibt `SUPABASE_AKTIV=false` die
empfohlene Einstellung.

### Dauerhafte Supabase-Anbindung (erst aktiv, wenn SUPABASE_AKTIV=true gesetzt ist)

Ist `SUPABASE_AKTIV=true` gesetzt UND `Supabase-Sicherung\config.json`
vollständig ausgefüllt, liest/schreibt das Backend die Krankmeldungen
dauerhaft im **bestehenden Supabase-Projekt** (demselben,
das die alte Netlify-Webapp unter `..\Background` verwendet) - genau nach
demselben Prinzip wie die alte Webseite: Login mit Benutzername+Passwort,
intern auf eine der beiden technischen E-Mail-Adressen abgebildet
(`dpfkb@gmx.de` / `bauschke.info@icloud.com`), Anmeldung bei Supabase Auth,
danach Zugriff über den öffentlichen anon-Key + das persönliche
Zugriffstoken. Passwörter werden dabei nie gespeichert, nur live an
Supabase weitergereicht - wie zuvor auch. Ein Service-Role-Key wird NICHT
benötigt.

Die nötigen Werte (Project URL, anon-Key, die beiden Login-E-Mails) stehen
bereits in `Supabase-Sicherung\config.json` - dieselbe Datei, die auch das
Sicherungs-Werkzeug verwendet.

Einmalige Einrichtung in Supabase (SQL Editor des Projekts):

1. `Supabase-Sicherung\sql\sick_report_audit.sql` ausführen (legt die Tabelle
   für das neue Änderungsprotokoll an, mit Policies für die beiden
   bestehenden Login-Konten).
2. Nur falls das Löschen einer Krankmeldung mit „HTTP 403“ fehlschlägt
   (die alte Webseite hatte absichtlich keine Löschfunktion, siehe
   `..\Background\README.txt`): zusätzlich
   `Supabase-Sicherung\sql\enable_delete_on_sick_reports.sql` ausführen.

Danach Backend neu starten (`start_app.bat`) - keine weiteren Code- oder
`.env`-Änderungen nötig (siehe `backend\app\repository.py`).

### Einzel-Logins für Mitarbeitende (neu, zusätzlich zu den Sammel-Logins)

Die bisherigen Sammel-Logins ADMIN/DRKFKB bleiben bestehen. Zusätzlich gibt
es jetzt eigene Logins je Mitarbeiter:in mit drei Rollenstufen
(`mitarbeiter` < `schichtleitung` < `admin`), sowie die neuen Module
Mitarbeiter-Stammdaten, Dienstplan-Import und Meldungen. Angelegt werden
die Logins über `POST /api/benutzer` bzw. das `Verwaltungstool` (Admin-Rolle).

**Wichtig:** Ohne die folgende einmalige Einrichtung funktionieren diese
neuen Module nicht (Fehler „Could not find the table … in the schema
cache“ im Server-Fenster) – die Sammel-Logins und Krankmeldungen laufen
aber unverändert weiter.

Einmalige Einrichtung in Supabase:

1. In Supabase Auth (Dashboard → Authentication → Users) ein drittes Konto
   für die Rollenstufe „Mitarbeiter" anlegen (beliebige E-Mail/Passwort,
   z. B. `mitarbeiter@fkb.local`).
2. `Supabase-Sicherung\sql\00_setup_alle_neuen_module.sql` öffnen, darin
   **alle 4 Vorkommen** von `MITARBEITER-EMAIL-HIER-EINTRAGEN` durch die
   neue E-Mail aus Schritt 1 ersetzen (Suchen&Ersetzen). Die beiden
   bestehenden Konten (`dpfkb@gmx.de` / `bauschke.info@icloud.com`) sind
   bereits eingetragen.
3. Das komplette Skript einmal im SQL Editor des Supabase-Projekts
   ausführen (legt alle vier neuen Tabellen + Rechte an und erweitert die
   Rollenbezeichnung im Änderungsprotokoll). Die einzelnen Dateien
   (`benutzer.sql`, `mitarbeiter.sql`, `dienstplan.sql`, `meldungen.sql`,
   `upgrade_audit_rollenstufen.sql`) enthalten denselben Inhalt einzeln,
   falls das lieber Schritt für Schritt gemacht werden soll.
4. `Supabase-Sicherung\config.json` um `"login_email_mitarbeiter"` ergänzen
   (siehe `config.example.json`).
5. In `backend\.env` die drei Service-Passwörter eintragen, mit denen sich
   das Backend selbst (nicht die Mitarbeitenden) bei Bedarf bei Supabase
   anmeldet: `TIER_SERVICE_PASSWORD_ADMIN`, `TIER_SERVICE_PASSWORD_SCHICHTLEITUNG`
   (Passwörter der beiden bestehenden Konten), `TIER_SERVICE_PASSWORD_MITARBEITER`
   (Passwort des neuen dritten Kontos).
6. Backend neu starten (`start_app.bat`).

Ohne diese Einrichtung funktionieren die Sammel-Logins unverändert weiter;
Einzel-Logins beantworten den Login-Versuch dann mit „Service-Konten
fehlen" (HTTP 503). Solange die Einzel-Logins noch nicht vollständig
eingerichtet sind, landet die Benutzerverwaltung (`benutzer`-Tabelle)
automatisch in der lokalen SQLite-Datenbank statt in Supabase.

## 3. Funktionsumfang

- Krankmeldung erfassen, bearbeiten, löschen (Rollenstufen Schichtleitung/Admin)
- Übersicht mit Filtern (Heute/Gestern/Monat/Zeitraum/Mitarbeitersuche)
- Rollenstufen **Mitarbeiter** (eigene Module), **Schichtleitung**
  (operative Module, entspricht der bisherigen Disposition-Rolle) und
  **Admin** (zusätzlich Careman-Status, Änderungsprotokoll,
  Benutzerverwaltung)
- CSV-Export der aktuellen Ansicht sowie des Änderungsprotokolls
- Änderungsprotokoll: jede Anlage/Änderung/Löschung wird mit
  Vorher-/Nachher-Werten gespeichert und bleibt auch nach Löschung
  eines Eintrags erhalten (nur für Admin sichtbar)
- Personal-Stammdaten (`/api/mitarbeiter`), Dienstplan-Excel-Import
  (`/api/dienstplan/import`, erkennt Krank-Meldungen und gelb markierte
  Bulli-Fahrer:innen wie im Nesk3-Projekt) und ein allgemeines
  Mitteilungsboard (`/api/meldungen`)
- Dienstplan: Standard-Sortierung T/T10/T8/sonstige Tag/N/N10/DT/DT3/DN/DN3,
  Erkennung abweichender Dienstzeiten, Filter (Suche/Status/Tag-Nacht-Anzeige),
  manuelle Korrektur (Krank/Bulli-Fahrer/Zeiten/Notiz) mit eigenem
  Änderungsprotokoll (`/api/dienstplan/audit`, nur Admin)

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

## 5. Verwaltungstool (Desktop-GUI)

Für Mitarbeiter-Stammdaten, Benutzerkonten (Einzel-Logins) und den
Dienstplan-Excel-Import gibt es ein eigenes Desktop-Tool, damit das
nicht zwingend über die Webseite laufen muss. Start über
**`start_verwaltungstool.bat`** – die Webapp (`start_app.bat`) muss dafür
bereits laufen, das Tool spricht dieselbe `/api/...`-Schnittstelle an
(eigener Login, nur für die Rolle Admin).

Funktionen:
- **Mitarbeiter-Stammdaten**: anlegen, bearbeiten, löschen.
- **Benutzerkonten**: Einzel-Logins anlegen (Benutzername, Passwort,
  Rolle mitarbeiter/schichtleitung/admin) und bearbeiten. Konten werden
  bewusst nicht gelöscht, sondern über „Aktiv" deaktiviert, damit das
  Änderungsprotokoll nachvollziehbar bleibt.
- **Dienstplan-Import**: Excel-Datei auswählen und importieren, inkl.
  Rückmeldung zu Anzahl Einträgen, Krank-Meldungen, Bulli-Fahrer:innen
  und unbekannten Dienstkürzeln.
- **Datenhaltung**: zeigt den aktuellen Modus (Lokal/Supabase) an,
  erlaubt das Umschalten (schreibt `backend\.env`) und den einmaligen
  Import vorhandener Supabase-Daten (Krankmeldungen + Änderungsprotokoll)
  in die lokale Datenbank - entweder live von Supabase (Rolle + Passwort)
  oder aus einem bereits vorhandenen Backup-Ordner
  (`Backups\Supabase\<Datum_Uhrzeit>\`, erstellt mit dem
  Supabase-Sicherungs-Werkzeug) ohne erneute Supabase-Anmeldung. Dieser
  Reiter spricht Supabase/die Backup-Dateien direkt an und schreibt
  direkt in die lokale SQLite-Datei - dafür muss die Webapp nicht laufen.

## 6. Datenschutz (unverändert wichtig)

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

## 7. Manuelle Befehle (optional, für Entwickler)

Falls die `.bat`-Dateien nicht verwendet werden sollen:

```powershell
cd backend
py -3 -m venv C:\pfad\ausserhalb\von\onedrive\venv
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m pip install -r requirements.txt
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Die API-Dokumentation (Swagger UI) ist bei laufendem Server erreichbar
unter: `http://127.0.0.1:8000/api/docs`
