"""SQLAlchemy-Modelle: Krankmeldungen und Änderungsprotokoll (Audit-Log)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Integer, String, Time

from .database import Base


class SickReport(Base):
    __tablename__ = "sick_reports"

    id = Column(Integer, primary_key=True, index=True)
    reported_at = Column(Date, nullable=False)
    employee = Column(String(150), nullable=False)
    sick_from = Column(Date, nullable=False)
    sick_to = Column(Date, nullable=False)
    call_at = Column(Time, nullable=True)
    accepted_by = Column(String(150), nullable=False, default="")
    notes = Column(String(1000), nullable=False, default="")
    careman_done = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Änderungsprotokoll. Einträge bleiben auch nach Löschung einer
    Krankmeldung erhalten (report_id ist bewusst ohne Fremdschlüssel-Zwang)."""

    __tablename__ = "sick_report_audit"

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    report_id = Column(Integer, nullable=True, index=True)
    action = Column(String(10), nullable=False)  # INSERT / UPDATE / DELETE
    actor_role = Column(String(20), nullable=False)  # admin / disposition
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)


class Benutzer(Base):
    """Einzel-Login für Mitarbeitende (nur im lokalen SQLite-Fallback-Modus
    ohne Supabase relevant - bei aktiver Supabase-Anbindung liegt dieselbe
    Tabelle stattdessen in Supabase, siehe Supabase-Sicherung\\sql\\benutzer.sql,
    damit alle PCs dieselben Logins sehen)."""

    __tablename__ = "benutzer"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    anzeigename = Column(String(150), nullable=False, default="")
    rolle = Column(String(20), nullable=False, default="mitarbeiter")  # mitarbeiter/disponent/schichtleitung/admin
    aktiv = Column(Boolean, nullable=False, default=True)
    # Selbstbedienungs-Passwort-Reset (siehe routers/auth.py:
    # /passwort-vergessen, /passwort-reset): die Antwort wird NIE im
    # Klartext gespeichert, nur als bcrypt-Hash (wie das Passwort selbst).
    sicherheitsfrage = Column(String(200), nullable=False, default="")
    sicherheitsantwort_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Mitarbeiter(Base):
    """Personal-Stammdaten."""

    __tablename__ = "mitarbeiter"

    id = Column(Integer, primary_key=True, index=True)
    vorname = Column(String(100), nullable=False)
    nachname = Column(String(100), nullable=False)
    personalnummer = Column(String(50), nullable=False, default="")
    funktion = Column(String(100), nullable=False, default="")
    email = Column(String(150), nullable=False, default="")
    telefon = Column(String(50), nullable=False, default="")
    aktiv = Column(Boolean, nullable=False, default=True)
    notizen = Column(String(1000), nullable=False, default="")
    # Weich gelöscht (siehe routers/mitarbeiter.py: delete_mitarbeiter/
    # restore_mitarbeiter) - analog zum Dienstplan (DienstplanEintrag.geloescht):
    # bleibt in der Datenbank erhalten statt endgültig entfernt zu werden,
    # damit u. a. doppelt angelegte Stammdatensätze (siehe
    # mitarbeiter_duplikate.py) gefahrlos bereinigt und bei Bedarf
    # wiederhergestellt werden können. geloescht_am/geloescht_durch werden
    # direkt auf dem Datensatz gehalten (zusätzlich zur ausführlicheren
    # Mitarbeiter-Historie/dem Änderungsprotokoll), damit im Frontend auch
    # ohne Verlaufsabfrage sofort sichtbar ist, wer wann gelöscht hat.
    geloescht = Column(Boolean, nullable=False, default=False)
    geloescht_am = Column(DateTime, nullable=True)
    geloescht_durch = Column(String(80), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DienstplanEintrag(Base):
    """Ein Dienstplan-Eintrag (eine Zeile aus einem importierten
    Tagesdienstplan-Excel, siehe dienstplan_parser.py)."""

    __tablename__ = "dienstplan"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(Date, nullable=False, index=True)
    mitarbeiter_name = Column(String(150), nullable=False)
    # Verknüpfung zu den Personal-Stammdaten (siehe mitarbeiter_matching.py),
    # bewusst ohne Fremdschlüssel-Zwang (wie bei den Audit-Tabellen): bleibt
    # beim Import auf None, wenn der Name keinem (eindeutigen) Stammdatensatz
    # zugeordnet werden konnte - Grundlage für die Mitarbeiter-Historie.
    mitarbeiter_id = Column(Integer, nullable=True, index=True)
    dienst_kategorie = Column(String(20), nullable=True)
    start_zeit = Column(String(5), nullable=True)  # "HH:MM"
    end_zeit = Column(String(5), nullable=True)
    ist_krank = Column(Boolean, nullable=False, default=False)
    ist_bulmorfahrer = Column(Boolean, nullable=False, default=False)
    # Manuell aus der Tag/Nacht/Dispo-Gesamtrechnung herausgenommen (z. B. bei
    # kurzfristigem Ausfall, siehe index.html "Ausschließen"/"Wieder
    # einrechnen"). Server-seitig gespeichert, damit es nach einem Neuladen
    # der Webseite erhalten bleibt (vorher nur clientseitig, ging beim
    # Neuladen verloren).
    ausgeschlossen = Column(Boolean, nullable=False, default=False)
    # Weich gelöscht (siehe routers/dienstplan.py: delete_dienstplan_eintrag/
    # restore_dienstplan_eintrag) - bleibt erhalten, damit sichtbar bleibt,
    # dass/wann ein Mitarbeiter aus dem Tagesdienstplan entfernt wurde.
    geloescht = Column(Boolean, nullable=False, default=False)
    geloescht_am = Column(DateTime, nullable=True)
    geloescht_durch = Column(String(80), nullable=False, default="")
    # Wird beim Wiederherstellen gesetzt, OHNE geloescht_am/geloescht_durch
    # zu löschen - so bleibt auch danach nachvollziehbar, wer/wann entfernt
    # UND wer/wann wiederhergestellt hat (siehe "Wiederhergestellt"-Badge
    # im Frontend).
    wiederhergestellt_am = Column(DateTime, nullable=True)
    wiederhergestellt_durch = Column(String(80), nullable=False, default="")
    # True = manuell über POST /api/dienstplan hinzugefügt statt aus einem
    # Excel-Import übernommen (siehe create_dienstplan_eintrag). Wer dies
    # getan hat, siehe hinzugefuegt_durch; wann, siehe created_at.
    manuell_hinzugefuegt = Column(Boolean, nullable=False, default=False)
    hinzugefuegt_durch = Column(String(80), nullable=False, default="")
    # Nachträglich erfasste Verspätung in Minuten (siehe routers/dienstplan.py:
    # "Ver."-Popup im Frontend), zusätzlich zur ursprünglich geplanten
    # start_zeit - diese bleibt dabei bewusst unverändert, damit geplante und
    # tatsächliche Zeit beide nachvollziehbar bleiben (siehe auch
    # /api/dienstplan/auswertung für die Zeitraum-Auswertung).
    verspaetung_minuten = Column(Integer, nullable=False, default=0)
    # Wer/wann die aktuelle Verspätung zuletzt erfasst/geändert hat - direkt
    # auf dem Datensatz gehalten (zusätzlich zum allgemeinen Dienstplan-
    # Änderungsprotokoll), damit die Auswertung das ohne Zusatzabfrage
    # anzeigen kann.
    verspaetung_erfasst_von = Column(String(80), nullable=False, default="")
    verspaetung_erfasst_am = Column(DateTime, nullable=True)
    notiz = Column(String(500), nullable=False, default="")
    quelle_datei = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Meldung(Base):
    """Allgemeines Mitteilungsboard (unabhängig von Krankmeldungen)."""

    __tablename__ = "meldungen"

    id = Column(Integer, primary_key=True, index=True)
    titel = Column(String(200), nullable=False)
    text = Column(String(4000), nullable=False, default="")
    autor = Column(String(150), nullable=False, default="")
    angeheftet = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DienstplanAudit(Base):
    """Änderungsprotokoll für Dienstplan-Einträge: Hinzufügen, Bearbeiten
    (Krank-Status, Dienstzeiten, Verspätung, Notizen), Entfernen und
    Wiederherstellen. Unveränderlich, bleibt auch nach Lösch-/Neuimport des
    zugehörigen Eintrags erhalten - Grundlage für den Tab "Änderungen" im
    Frontend (siehe routers/dienstplan.py) und die automatisch gepflegte
    Excel-Datei unter Backups/Tagesdienstpläne/Aenderungen/<Jahr>/<Monat>/."""

    __tablename__ = "dienstplan_audit"

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    dienstplan_id = Column(Integer, nullable=True, index=True)
    # Dienstplan-Tag (DienstplanEintrag.datum) des betroffenen Eintrags -
    # NICHT dasselbe wie event_at (der Zeitpunkt der Änderung kann auf
    # einem anderen Kalendertag liegen, z. B. nachträgliche Korrektur eines
    # älteren Tages). Grundlage für die Tag-/Zeitraum-Auswahl im Tab
    # "Änderungen" (siehe routers/dienstplan.py: list_dienstplan_audit) und
    # die automatische Tagesdatei unter Aenderungen/<Jahr>/<Monat>/.
    datum = Column(Date, nullable=True, index=True)
    mitarbeiter_name = Column(String(150), nullable=False, default="")
    # HINZUGEFÜGT / BEARBEITET / ENTFERNT / WIEDERHERGESTELLT (siehe
    # routers/dienstplan.py) - frueher nur "UPDATE", daher absichtlich
    # geraeumig genug fuer die ausfuehrlicheren Bezeichnungen.
    action = Column(String(30), nullable=False)
    actor_role = Column(String(20), nullable=False)
    actor_username = Column(String(80), nullable=False, default="")
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)


class MitarbeiterEreignis(Base):
    """Historie je Mitarbeiter:in (siehe mitarbeiter_historie.py): hält u. a.
    fest, wie oft/wann jemand krank gemeldet wurde und wann sich die
    Stammdaten geändert haben. mitarbeiter_name ist ein Abbild zum
    Ereigniszeitpunkt (bleibt lesbar, auch wenn der Stammdatensatz später
    umbenannt oder gelöscht wird) - mitarbeiter_id bewusst ohne
    Fremdschlüssel-Zwang, analog zu den bestehenden Audit-Tabellen."""

    __tablename__ = "mitarbeiter_ereignis"

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    mitarbeiter_id = Column(Integer, nullable=True, index=True)
    mitarbeiter_name = Column(String(150), nullable=False, default="")
    # z. B. krank_gemeldet / krank_storniert / dienstplan_krank_aufgehoben /
    # stammdaten_angelegt / stammdaten_geaendert / stammdaten_geloescht
    ereignis_typ = Column(String(40), nullable=False)
    beschreibung = Column(String(500), nullable=False, default="")
    # z. B. "sick_report" / "dienstplan" / "mitarbeiter"
    bezug_typ = Column(String(30), nullable=True)
    bezug_id = Column(String(50), nullable=True)
    actor_username = Column(String(80), nullable=False, default="")
    actor_role = Column(String(20), nullable=False, default="")
    details = Column(JSON, nullable=True)


class BenutzerAktivitaet(Base):
    """Logfile je Benutzerkonto (siehe aktivitaet.py): hält fest, welcher
    Account wann an- oder abgemeldet war und welche Aktion (anlegen/
    bearbeiten/löschen) er in welchem Bereich ausgeführt hat - unabhängig
    von den fachlichen Änderungsprotokollen (sick_report_audit,
    dienstplan_audit), die nur Vorher/Nachher-Werte je Datensatz zeigen."""

    __tablename__ = "benutzer_aktivitaet"

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    username = Column(String(80), nullable=False, default="", index=True)
    rolle = Column(String(20), nullable=False, default="")
    # z. B. LOGIN / LOGIN_FEHLGESCHLAGEN / LOGOUT / CREATE / UPDATE / DELETE / IMPORT
    aktion = Column(String(30), nullable=False)
    # z. B. Anmeldung / Krankmeldungen / Mitarbeiter-Stammdaten /
    # Benutzerkonten / Dienstplan / Meldungen
    bereich = Column(String(60), nullable=False, default="")
    entity_typ = Column(String(30), nullable=True)
    entity_id = Column(String(50), nullable=True)
    entity_bezeichnung = Column(String(200), nullable=False, default="")
    beschreibung = Column(String(500), nullable=False, default="")
    details = Column(JSON, nullable=True)
