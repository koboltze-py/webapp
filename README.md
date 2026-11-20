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
│   ├── Supabase/               Zielordner der Supabase-Sicherungen (ein Unterordner je Lauf)
│   ├── App/                    Vollstaendige Software-Backups (manuell erstellt)
│   ├── Mds/                     Technische Dokumentation als Backup-Snapshot
│   ├── Tagesdienstpläne/        Automatischer Dienstplan-Excel-Schnappschuss je Tag
│   │                             (<Jahr>\<MM>_<Monat>\<Tag>.xlsx, wird bei jedem
│   │                             Import/jeder Aenderung ueberschrieben, kein
│   │                             separater Ordner/keine separate Datei je Aenderung)
│   └── Tagesprotokoll/          Fortlaufendes, fuer Menschen lesbares Aenderungsprotokoll
│                                 je Tag (gleiche Ordnerstruktur wie Tagesdienstplaene,
│                                 aber WACHSEND: jede Aenderung wird als neue Zeile
│                                 angehaengt statt ueberschrieben, siehe Abschnitt 3)
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
| Disposition (Rollenstufe "Disponent", siehe Abschnitt 8) | `DRKFKB` | `Disposition` |
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
4. Zusätzlich (für Mitarbeiter-Historie + Benutzerprotokoll, siehe
   Abschnitt 3):
   `Supabase-Sicherung\sql\mitarbeiter_historie_und_benutzer_aktivitaet.sql`
   ausführen (ergänzt `dienstplan.mitarbeiter_id` sowie die beiden neuen
   Tabellen `mitarbeiter_ereignis` und `benutzer_aktivitaet`).
5. `Supabase-Sicherung\config.json` um `"login_email_mitarbeiter"` ergänzen
   (siehe `config.example.json`).
6. In `backend\.env` die drei Service-Passwörter eintragen, mit denen sich
   das Backend selbst (nicht die Mitarbeitenden) bei Bedarf bei Supabase
   anmeldet: `TIER_SERVICE_PASSWORD_ADMIN`, `TIER_SERVICE_PASSWORD_DISPONENT`
   (Passwörter der beiden bestehenden Konten), `TIER_SERVICE_PASSWORD_MITARBEITER`
   (Passwort des neuen dritten Kontos). Die neue Rollenstufe "schichtleitung"
   (siehe Abschnitt 8) nutzt dabei automatisch dasselbe Supabase-Konto wie
   "admin" (kein eigenes Service-Passwort nötig).
7. Backend neu starten (`start_app.bat`).

Ohne diese Einrichtung funktionieren die Sammel-Logins unverändert weiter;
Einzel-Logins beantworten den Login-Versuch dann mit „Service-Konten
fehlen" (HTTP 503). Solange die Einzel-Logins noch nicht vollständig
eingerichtet sind, landet die Benutzerverwaltung (`benutzer`-Tabelle)
automatisch in der lokalen SQLite-Datenbank statt in Supabase.

## 3. Funktionsumfang

- Krankmeldung erfassen, bearbeiten, löschen (Rollenstufen Disponent/
  Schichtleitung/Admin)
- Übersicht mit Filtern (Heute/Gestern/Monat/Zeitraum/Mitarbeitersuche)
- 4 Rollenstufen **Mitarbeiter** < **Disponent** < **Schichtleitung** <
  **Admin** - Details und Rechte je Stufe siehe Abschnitt 8
- CSV-Export der aktuellen Ansicht sowie des Änderungsprotokolls
- Änderungsprotokoll: jede Anlage/Änderung/Löschung wird mit
  Vorher-/Nachher-Werten gespeichert und bleibt auch nach Löschung
  eines Eintrags erhalten (ab Schichtleitung sichtbar)
- Personal-Stammdaten (`/api/mitarbeiter`), Dienstplan-Excel-Import
  (`/api/dienstplan/import`, erkennt Krank-Meldungen und gelb markierte
  Bulli-Fahrer:innen wie im Nesk3-Projekt) und ein allgemeines
  Mitteilungsboard (`/api/meldungen`)
- Dienstplan: Standard-Sortierung T/T10/T8/sonstige Tag/N/N10/DT/DT3/DN/DN3,
  Erkennung abweichender Dienstzeiten, Filter (Suche/Status/Tag-Nacht-Anzeige),
  manuelle Korrektur (Krank/Bulli-Fahrer/Zeiten/Notiz) mit eigenem
  Änderungsprotokoll (`/api/dienstplan/audit`, Tab "Änderungen", für ALLE
  Rollen). In der
  Standardsortierung wird - wie die bestehende "Dispo"-Trennlinie - auch
  der Übergang von Tag- zu Nachtdienst optisch klar abgesetzt.
- Dienstplan: einzelne Personen können unabhängig von einem Excel-Import
  manuell hinzugefügt (`POST /api/dienstplan`) oder weich entfernt werden
  (`DELETE /api/dienstplan/{id}`, `POST /api/dienstplan/{id}/wiederherstellen`
  zum Rückgängigmachen) - ab Rolle Disponent. Hinzugefügte/entfernte
  Einträge bleiben über Badges "Hinzugefügt"/"Entfernt" sichtbar; entfernte
  Einträge sind standardmäßig ausgeblendet, über die Checkbox "Entfernte
  anzeigen" aber weiterhin einsehbar.
- Dienstplan: Zusammenfassung Tag/Nacht/Dispo-Mitarbeiter im Dienst (inkl.
  Krank-Anzahl je Gruppe, Aufteilung nach Dienstart wie T/T10/T8/N/N10,
  Erkennung von Zeiten die mehr als 1 Std. vom Rest der eigenen Dienstart
  abweichen). Rufbereitschaft (Dienst "R") und Kranke zählen nicht als "im
  Dienst" mit. Einzelne Mitarbeitende können per Button aus der
  Gesamtrechnung ausgeschlossen bzw. wieder einbezogen werden (serverseitig
  gespeichert je Dienstplan-Eintrag, bleibt also auch nach einem Neuladen
  der Webseite erhalten, ab Rolle Disponent). Excel-Export eines Tages
  (`/api/dienstplan/export`), **1:1 im Format der echten
  Tagesdienstplan-Vorlage** (Zellen, Rahmen, Schriftarten, Farben,
  Zahlenformate - gegen eine echte Datei abgeglichen, siehe
  `backend/app/dienstplan_export.py`). Bei jedem Excel-Import **und**
  jeder manuellen Änderung wird automatisch ein solcher Export unter
  `Backups\Tagesdienstpläne\<Jahr>\<MM>_<Monat>\<Tag>.xlsx` gespeichert
  (überschreibt den vorherigen Stand desselben Tages - der laufende
  Änderungsverlauf steht stattdessen im Tagesprotokoll, siehe Abschnitt 8).
  Namens-Autovervollständigung aus den Mitarbeiter-Stammdaten im
  Krankmeldungs-Formular
- Dienstplan-Import: jeder importierte Name wird automatisch den
  Mitarbeiter-Stammdaten zugeordnet (exakter Treffer, erkannter
  Vor-/Nachname-Dreher oder eindeutiger Tippfehler-Treffer, siehe
  `backend/app/mitarbeiter_matching.py`). Nicht zuordenbare oder nur
  unsicher zugeordnete Namen werden im Importergebnis gesondert
  aufgeführt (zur manuellen Prüfung), blockieren den Import aber nicht.
- Krank-Status im Dienstplan entfernen: Wird eine Person im Dienstplan
  wieder auf "nicht krank" gesetzt, wird vorher gefragt, ob die passende
  laufende Krankmeldung ebenfalls gelöscht werden soll (siehe
  `routers/dienstplan.py`, Feld `auch_krankmeldung_loeschen`)
- **Mitarbeiter-Historie**: je Mitarbeiter:in wird nachvollziehbar
  protokolliert, wie oft/wann krank gemeldet wurde (inkl. Kranktage
  gesamt), wann Krankmeldungen storniert/gelöscht wurden und wann sich die
  Stammdaten geändert haben (`/api/mitarbeiter/{id}/historie`, siehe
  `backend/app/mitarbeiter_historie.py`). Sichtbar über den Button
  "Verlauf" in der Mitarbeiter-Stammdaten-Tabelle (Webapp, ab
  Schichtleitung) sowie im Verwaltungstool.
- **Benutzerprotokoll** (Logfile je Account): protokolliert für jedes
  Benutzerkonto An-/Abmeldungen sowie Anlegen/Bearbeiten/Löschen über alle
  Module hinweg (Krankmeldungen, Mitarbeiter-Stammdaten, Benutzerkonten,
  Dienstplan, Meldungen), siehe `backend/app/aktivitaet.py` und
  `/api/audit/benutzerprotokoll` (nur Admin).
- Beide Protokolle (Mitarbeiter-Historie und Benutzerprotokoll) lassen
  sich im **Verwaltungstool** als Excel-Datei exportieren (Reiter
  "Historie & Protokolle").
- Dienstplan-Krank-Popup: Wird ein Eintrag im Dienstplan auf "Krank"
  gesetzt (manuell oder durch einen Excel-Import erkannt), erscheint ein
  Popup zum direkten Anlegen der passenden Krankmeldung (vorausgefüllt mit
  Name/Datum), mit der Möglichkeit, das Anlegen auch abzulehnen. Nach
  einem Import mit mehreren noch nicht gemeldeten Krankheitsfällen werden
  die Popups nacheinander (Warteschlange mit Zähler) angeboten.
- Mehrtägige Krankmeldungen werden auch an Tagen ohne Excel-Import als
  schreibgeschützte "virtuelle" Dienstplan-Einträge angezeigt (Kennzeichnung
  "Ohne Dienstplan"), sodass länger andauernde Krankheiten nicht aus dem
  Blick geraten

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
- **Mitarbeiter-Stammdaten**: anlegen, bearbeiten, weich löschen/
  wiederherstellen (Checkbox "Entfernte anzeigen", Buttons "Löschen
  (weich)"/"Wiederherstellen" - entspricht derselben weichen Löschung wie
  in der Webapp, siehe Abschnitt "Mitarbeiter-Stammdaten: Suche,
  Dubletten-Erkennung, weiches Löschen"), sowie je Mitarbeiter:in den
  Verlauf anzeigen (Button "Verlauf anzeigen": wie oft/wann krank,
  Stammdaten-Änderungen inkl. Löschen/Wiederherstellen).
- **Stammdaten-Import**: durchsucht einen Ordner mit echten Tagesdienstplan-
  Excel-Dateien (z. B. `04_Tagesdienstpläne`) rekursiv nach Vor-/Nachnamen
  (Unterordner `03_Krankmeldungen` wird ausgeschlossen) und legt daraus
  fehlende Mitarbeiter-Stammdaten an (Duplikate werden übersprungen,
  Vorschau vor dem Anlegen). Dateien, die aufgrund defekter/ungewöhnlicher
  Ordnerstrukturen nicht lesbar sind, werden übersprungen und im Protokoll
  als Fehler gezählt statt den Scan abzubrechen.
- **Benutzerkonten**: Einzel-Logins anlegen (Benutzername, Passwort,
  Rolle mitarbeiter/schichtleitung/admin) und bearbeiten. Konten werden
  bewusst nicht gelöscht, sondern über „Aktiv" deaktiviert, damit das
  Änderungsprotokoll nachvollziehbar bleibt.
- **Dienstplan-Import**: Excel-Datei auswählen und importieren, inkl.
  Rückmeldung zu Anzahl Einträgen, Krank-Meldungen, Bulli-Fahrer:innen,
  unbekannten Dienstkürzeln sowie nicht oder nur unsicher den
  Mitarbeiter-Stammdaten zugeordneten Namen.
- **Historie & Protokolle**: Export der kompletten Mitarbeiter-Historie
  (alle Mitarbeitenden) sowie des Benutzerprotokolls (optional gefiltert
  nach Benutzername) als Excel-Datei; das Benutzerprotokoll lässt sich
  zusätzlich direkt in einer Tabelle einsehen.
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
- Bei den weiterhin bestehenden gemeinsamen Sammel-Logins (ADMIN/DRKFKB)
  dokumentiert das Änderungsprotokoll nur die Rolle und den Zeitpunkt,
  keine individuelle Person. Bei Einzel-Logins je Mitarbeiter:in wird
  zusätzlich der jeweilige Benutzername protokolliert (Dienstplan-
  Änderungsprotokoll, Mitarbeiter-Historie, Benutzerprotokoll) - das
  Benutzerprotokoll zeichnet dabei An-/Abmeldungen sowie
  Anlegen/Bearbeiten/Löschen je Account auf und sollte daher nur
  berechtigten Schichtleitungs-/Admin-Personen zugänglich sein.
- Keine Diagnosen in Bemerkungen erfassen.
- Standardpasswörter vor Produktivbetrieb ändern (`backend\.env`).
- Sicherungsordner (`Backups\Supabase`) und die Datenbankdatei
  (`backend\data\krankmeldungen.db`) nur geschützt ablegen/freigeben.
- Vor Produktivbetrieb mit den Datenschutzverantwortlichen klären:
  Rechtsgrundlage, TOMs, Aufbewahrung und Löschkonzept, Zugangsberechtigung.

## 8. Neu in version2.1

### Rollenmodell (4 Stufen statt vormals 3)

| Stufe | Beispiel-Login | Rechte |
|---|---|---|
| **Mitarbeiter** | Einzel-Login | nur eigene Module (Heute, Meldungen lesen) |
| **Disponent** | `DRKFKB` (Sammel-Login) | zusätzlich: Krankmeldungen anlegen/bearbeiten/löschen, Mitarbeiter-Stammdaten anlegen/bearbeiten/ausschließen, Dienstplan importieren/exportieren/bearbeiten/manuell hinzufügen oder entfernen, Meldungen verfassen/löschen. **Kein** Zugriff auf Mitarbeiter-Verlauf, Benutzerverwaltung oder Änderungsprotokolle. |
| **Schichtleitung** | nur Einzel-Login | alles, was Admin auch kann, **außer** den Careman-Status zu setzen/umzuschalten |
| **Admin** | `ADMIN` (Sammel-Login) | uneingeschränkt, inkl. Careman-Status |

Bestehende Einzel-Login-Konten mit der alten Rolle `schichtleitung`
(Bedeutung vor version2.1: die operative Stufe, heute `disponent`) wurden
beim ersten Start automatisch auf `disponent` umbenannt, damit sich ihre
Rechte nicht unbeabsichtigt erhöhen - die neue, höherwertige Stufe
`schichtleitung` muss bewusst neu vergeben werden (Einstellungen ->
Benutzerverwaltung, oder Verwaltungstool).

### Benutzerverwaltung direkt in der Webapp

Einstellungen -> Benutzerverwaltung (ab Rolle Schichtleitung) erlaubt nun
direkt in der Webapp das Anlegen/Bearbeiten von Einzel-Login-Konten
(Benutzername, Anzeigename, Rolle, Passwort, Sicherheitsfrage) - ohne das
separate Verwaltungstool. Konten werden wie gehabt nicht gelöscht,
sondern deaktiviert.

### Passwort-Reset über Sicherheitsfrage

Beim Anlegen/Bearbeiten eines Kontos kann eine Sicherheitsfrage +
Antwort hinterlegt werden (Antwort wird nur als bcrypt-Hash gespeichert,
Groß-/Kleinschreibung und Leerzeichen spielen beim Vergleich keine
Rolle). Über den Link "Passwort vergessen?" auf der Login-Seite kann
jede:r Mitarbeiter:in sein/ihr Passwort danach selbst zurücksetzen
(`POST /api/auth/passwort-vergessen`, `POST /api/auth/passwort-reset`).
Ohne hinterlegte Sicherheitsfrage bleibt nur der Admin/Schichtleitungs-
Reset über die Benutzerverwaltung.

### Mitarbeiter-Stammdaten: Suche, Dubletten-Erkennung, weiches Löschen

- Suchfeld über der Stammdaten-Tabelle (`GET /api/mitarbeiter?suche=...`).
- Karte "Mögliche Dubletten" (ab Rolle Disponent, Button "Prüfen"):
  gruppiert Stammdatensätze mit exakt gleichem oder sehr ähnlichem Namen
  (Tippfehler-Ähnlichkeitsvergleich, siehe `backend/app/mitarbeiter_duplikate.py`)
  zur manuellen Prüfung - direkt mit "Bearbeiten"/"Löschen" korrigierbar;
  die Liste aktualisiert sich sofort nach dem Löschen/Wiederherstellen.
- **Weiches Löschen**: "Löschen" entfernt einen Stammdatensatz nicht
  endgültig, sondern markiert ihn als entfernt (`geloescht`,
  `geloescht_am`, `geloescht_durch`, siehe `models.py:Mitarbeiter`) -
  analog zum bestehenden Dienstplan-Verhalten. Die Checkbox "Entfernte
  anzeigen" blendet weich gelöschte Einträge ein, dort direkt mit Pill
  "Entfernt" (Tooltip: wer/wann) und Button "Wiederherstellen"
  (`POST /api/mitarbeiter/{id}/wiederherstellen`). Wer/wann angelegt,
  geändert, gelöscht oder wiederhergestellt hat, bleibt zusätzlich im
  Verlauf (`/api/mitarbeiter/{id}/historie`) und im Änderungsprotokoll
  nachvollziehbar. Auch im **Verwaltungstool** (Desktop) verfügbar (Reiter
  "Mitarbeiter-Stammdaten": Checkbox "Entfernte anzeigen", Buttons
  "Löschen (weich)"/"Wiederherstellen").
- **Strikte Namensvalidierung**: Bei einer Krankmeldung ("Meldender") und
  beim manuellen Hinzufügen zum Dienstplan ist nur noch die Eingabe eines
  Namens möglich, der exakt einem aktiven Mitarbeiter-Stammdatensatz
  entspricht (clientseitig per Vorschlagsliste geprüft, serverseitig über
  `backend/app/mitarbeiter_matching.ist_mitarbeiter_name_bekannt`
  zusätzlich erzwungen) - verhindert neue, nicht gepflegte Namen und hilft,
  die Stammdaten auf Dauer dubletten- und fehlerfrei zu halten. Der
  Excel-Import des Dienstplans bleibt davon bewusst unberührt (dort
  weiterhin tolerant, siehe unsichere Zuordnungen).

### Dienstplan: Mitarbeiter manuell hinzufügen/entfernen

Über den Button "+ Mitarbeiter hinzufügen" lässt sich eine Person
unabhängig von einem Excel-Import zu einem Tagesdienstplan hinzufügen;
über "Entfernen" in der Aktionsspalte wird sie weich entfernt (bleibt in
der Datenbank, Badge "Entfernt", über "Wiederherstellen" rückgängig
machbar). Die Checkbox "Entferne Einträge: Entfernte anzeigen" blendet
weich gelöschte Einträge ein/aus. Manuell hinzugefügte Einträge tragen
zusätzlich das Badge "Hinzugefügt". Beides ab Rolle Disponent bedienbar.
Alle drei Aktionen (Hinzufügen/Entfernen/Wiederherstellen) sind direkt in
der Tabelle nachvollziehbar: die Badges "Hinzugefügt"/"Entfernt"/
"Wiederhergestellt" zeigen per Tooltip, **wer** es **wann** gemacht hat
(`hinzugefuegt_durch`, `geloescht_am`/`geloescht_durch`,
`wiederhergestellt_am`/`wiederhergestellt_durch`, siehe
`models.py:DienstplanEintrag`) - zusätzlich zum ausführlichen Tab
"Änderungen" (siehe unten).

### Dienstplan: Tab "Änderungen" (alle Änderungen nachvollziehen)

Neben "+ Mitarbeiter hinzufügen" öffnet der Button **"Änderungen"** (für
ALLE angemeldeten Rollen) eine Übersicht aller Dienstplan-Änderungen
(Hinzugefügt/Bearbeitet/Entfernt/Wiederhergestellt) - standardmäßig für
den gerade angezeigten Tag, über "Von"/"Bis" aber auch für einen beliebigen
Zeitraum. Je Zeile: betroffener Tag, Zeitpunkt der Änderung, Aktion,
Mitarbeiter:in, durchführender Account und die konkreten Feldänderungen
(`GET /api/dienstplan/audit?von=...&bis=...`, siehe
`models.py:DienstplanAudit`) - inkl. Excel-Export
(`/api/dienstplan/audit/export`).

Zusätzlich wird bei JEDER Änderung automatisch eine Excel-Datei unter
`Backups\Tagesdienstpläne\Aenderungen\<Jahr>\<MM>_<Monat>\<Tag>.xlsx`
angelegt bzw. überschrieben (analog zum Tagesdienstplan-Schnappschuss,
siehe oben) - sie wird dabei jedes Mal komplett aus der vollständigen,
in der Datenbank gespeicherten Änderungshistorie dieses Tages neu
aufgebaut, sodass trotz des Überschreibens nichts verloren geht (siehe
`routers/dienstplan.py:_sichere_aenderungen_snapshot`).

### Unbekannte Dienstkürzel

Dienst-Kürzel, die das System nicht kennt (siehe
`dienstplan_parser.BEKANNTE_KUERZEL`, z. B. durch Tippfehler oder neue,
noch nicht hinterlegte Kürzel), werden direkt in der Dienstplan-Zeile mit
einem Warn-Badge "Unbekanntes Kürzel" markiert (`GET
/api/dienstplan/bekannte-kuerzel`) - zusätzlich zur bisherigen
Sammelmeldung beim Excel-Import.

### Dienstplan-Import: Namen, die nicht/unsicher zu den Stammdaten passen

Jeder Name aus einem Excel-Import wird gegen die Mitarbeiter-Stammdaten
abgeglichen (siehe `mitarbeiter_matching.ordne_mitarbeiter_zu`). Der
Import wird dadurch NIE blockiert - auch unklare Treffer werden als
Dienstplan-Eintrag angelegt -, aber unter "Tagesdienstplan importieren"
erscheinen danach zwei handlungsfähige Hinweis-Listen:

- **"Nicht den Stammdaten zugeordnet"**: Der Name kam in den
  Stammdaten gar nicht vor. Über den Button "Jetzt anlegen" springt man
  direkt zu "Mitarbeiter:in anlegen" (Personal-Tab), mit Vor-/Nachname
  aus der Excel-Zelle vorbelegt - nach Prüfen und Speichern ist die
  Person für künftige Importe/Eingaben bekannt (dieser eine Dienstplan-
  Eintrag selbst wird dabei nicht automatisch nachträglich verknüpft).
- **"Unsichere Zuordnung - bitte prüfen"**: Der Name wurde nur über
  Tippfehler-/Dreher-Erkennung einem Stammdatensatz zugeordnet (diese
  Zuordnung ist zu diesem Zeitpunkt bereits aktiv). Über "Bestätigen"
  (`POST /api/dienstplan/{id}/zuordnung/bestaetigen`) bleibt sie
  bestehen - wird aber jetzt, anders als zuvor, mit Wer/Wann im
  Änderungsprotokoll festgehalten. Über "Ablehnen" (`POST
  /api/dienstplan/{id}/zuordnung/ablehnen`) wird die Zuordnung wieder
  gelöst (`mitarbeiter_id` → `None`) und man springt direkt zu
  "Mitarbeiter:in anlegen", vorbelegt mit dem ursprünglichen Namen aus
  der Excel-Zelle.

Beide Aktionen erzeugen - wie alle anderen Dienstplan-Änderungen - einen
Eintrag im Tab "Änderungen" und im Tagesprotokoll (siehe unten).

### Verspätungen erfassen ("Ver."-Button) und auswerten

Neben "Bearbeiten" gibt es je Dienstplan-Eintrag (ab Rolle Disponent)
einen Button "Ver.", der ein Popup zum Erfassen einer Verspätung öffnet:
Schnellwahl in 5-Minuten-Schritten bis 60 Minuten sowie eine manuelle
Eingabe (auch darüber hinaus), mit Live-Vorschau der tatsächlichen
Beginnzeit. Die Verspätung wird zusätzlich zur geplanten Beginnzeit
gespeichert (`verspaetung_minuten`, siehe `models.py:DienstplanEintrag`) -
die geplante Zeit selbst bleibt unverändert. Zusätzlich wird erfasst,
welcher Account die Verspätung wann eingetragen hat
(`verspaetung_erfasst_von`/`verspaetung_erfasst_am`). In der
Dienstplan-Tabelle erscheint sie als Badge direkt neben "Beginn" (Tooltip:
Minuten + erfassender Account + Zeitpunkt).

Der neue Tab **"Dienstplan Auswertung"** (Hauptnavigation, ab Rolle
Disponent) wertet für einen frei wählbaren Zeitraum sowohl **Verspätungen**
als auch **Krankmeldungen** aus (`GET /api/dienstplan/auswertung?von=...&bis=...`),
jeweils übersichtlich in zwei Tabellen:
- Zusammenfassung je Mitarbeiter:in (Anzahl + Summe Minuten bzw. Anzahl +
  Kranktage gesamt)
- Einzelne Vorfälle mit allen Details - bei Verspätungen: Tag, Dienst,
  geplanter Beginn, Minuten, **wer sie wann erfasst hat**; bei
  Krankmeldungen: Zeitraum, Kranktage, angenommen von, gemeldet am.

Excel-Export (`/api/dienstplan/auswertung/export`) liefert eine
Arbeitsmappe mit zwei Tabellenblättern ("Verspätungen", "Krankmeldungen")
mit denselben Detaildaten. Verspätungen gibt es nur als manuell erfasste
Werte (siehe oben) - es gibt im System keine automatische "Ist-Zeit"-
Quelle (z. B. Stempeluhr), gegen die eine Abweichung automatisch berechnet
werden könnte.

### Klare Tag-/Nacht-Trennung im Dienstplan

In der Standardsortierung wird jetzt - genau wie die bestehende
"Dispo"-Trennlinie - auch der Übergang von Tag- zu Nachtdienst mit einer
eigenen Trennzeile ("Nachtdienst") markiert.

### Tagesprotokoll (neu, `Backups\Tagesprotokoll`)

Zusätzlich zum Tagesdienstplan-Schnappschuss (siehe Abschnitt 3, wird je
Tag überschrieben) wird unter `Backups\Tagesprotokoll\<Jahr>\<MM>_<Monat>\<Tag>.xlsx`
ein fortlaufendes, für Menschen lesbares Änderungsprotokoll geführt: jeder
Import und jede manuelle Änderung (bearbeitet/hinzugefügt/entfernt/
wiederhergestellt) eines Dienstplan-Eintrags wird dort als neue Zeile
(Zeitpunkt, Aktion, Mitarbeiter, Durchgeführt von, Rolle, Beschreibung)
angehängt - die Datei wächst über den Tag, nichts wird überschrieben.

### Datensicherheit: Erkennung von OneDrive-Synchronisationskonflikten

Die lokale Datenbank (`backend\data\krankmeldungen.db`) liegt bewusst
innerhalb des mit OneDrive synchronisierten Projektordners (siehe
Abschnitt 2) und kann daher - wenn die App kurz hintereinander auf zwei
Geräten läuft - Ziel eines OneDrive-Synchronisationskonflikts werden:
OneDrive legt dann eine Konfliktkopie an (z. B. `krankmeldungen-PCNAME.db`)
und die eigentlich aktive Datei fällt unbemerkt auf einen älteren Stand
zurück (Ursache für scheinbar verschwundene Dienstplan-Importe/
Krankmeldungen). Das Backend prüft daher bei jedem Start den
`backend\data`-Ordner auf weitere `*.db`-Dateien und warnt lautstark
(Konsole **und** Hinweisleiste auf der "Heute"-Seite, ab Rolle
Schichtleitung, `GET /api/system/warnungen`), falls eine gefundene
Konfliktkopie neuer ist als die aktive Datenbank. **Wichtig:** Die App
sollte weiterhin nur auf einem PC gleichzeitig laufen (siehe Abschnitt 2) -
diese Prüfung macht ein bereits aufgetretenes Problem nur sichtbar, sie
verhindert es nicht automatisch und führt auch keine automatische
Daten-Zusammenführung durch. Bei einer Warnung: Server beenden, mit
einem/einer Administrator:in die beiden Datenbankdateien vergleichen
(z. B. mit dem Verwaltungstool oder einem SQLite-Browser) und die
Konfliktkopie erst danach manuell entfernen.

### Branding "NeSk - Illuminate" und Darkmode

Die Seitenleiste zeigt statt "DRK FKB" das NeSk-Logo
(`frontend\assets\nesk-logo.png`, Quelle: `Nesk\Nesk3\Daten\Logo\nesk3.ico`)
zusammen mit dem Schriftzug "NeSk - Illuminate". Das Browser-Tab-Icon
(Favicon) nutzt ebenfalls dieses Logo (`frontend\assets\favicon.ico`).
Oben rechts (Topbar bzw. auf dem Anmeldebildschirm) gibt es einen
Mond-/Sonnen-Button zum Umschalten zwischen Hell- und Dunkelmodus; die
Wahl wird pro Browser in `localStorage` gespeichert und bleibt daher über
Neuladen/Neuanmeldung hinweg erhalten (für alle Nutzer:innen unabhängig
von der Rolle). Technisch steuert ein `data-theme`-Attribut auf `<html>`
einen Satz CSS-Variablen (`--bg`, `--surface`, `--ink`, `--border`,
`--pill-*`, usw.) in `frontend\index.html`; neue Komponenten sollten diese
Variablen statt fest codierter Farben verwenden, damit sie automatisch
dunkelmodustauglich sind.

## 9. Manuelle Befehle (optional, für Entwickler)

Falls die `.bat`-Dateien nicht verwendet werden sollen:

```powershell
cd backend
py -3 -m venv C:\pfad\ausserhalb\von\onedrive\venv
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m pip install -r requirements.txt
C:\pfad\ausserhalb\von\onedrive\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Die API-Dokumentation (Swagger UI) ist bei laufendem Server erreichbar
unter: `http://127.0.0.1:8000/api/docs`
