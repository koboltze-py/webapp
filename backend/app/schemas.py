"""Pydantic-Schemas für Request/Response der API."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class ReportBase(BaseModel):
    reported_at: date
    employee: str = Field(..., min_length=1, max_length=150)
    sick_from: date
    sick_to: date
    call_at: Optional[time] = None
    accepted_by: str = Field("", max_length=150)
    notes: str = Field("", max_length=1000)
    careman_done: bool = False


class ReportCreate(ReportBase):
    pass


class ReportUpdate(ReportBase):
    pass


class ReportOut(ReportBase):
    model_config = ConfigDict(from_attributes=True)

    # int bei lokaler SQLite-Datenbank, str (UUID) bei dauerhafter Supabase-Anbindung
    id: Union[int, str]
    created_at: datetime
    updated_at: datetime


class CaremanUpdate(BaseModel):
    careman_done: bool


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    event_at: datetime
    report_id: Optional[Union[int, str]]
    action: str
    actor_role: str
    old_data: Optional[dict]
    new_data: Optional[dict]


# --- Benutzer (Einzel-Logins) -------------------------------------------

# Siehe deps.py für die genaue Rechtebeschreibung je Stufe.
TIER_ROLES = ("mitarbeiter", "disponent", "schichtleitung", "admin")


class BenutzerCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=6, max_length=200)
    anzeigename: str = Field("", max_length=150)
    rolle: str = Field("mitarbeiter")
    aktiv: bool = True
    # Für die Selbstbedienungs-Passwort-Reset-Funktion (siehe
    # routers/auth.py: /passwort-vergessen, /passwort-reset). Beide optional,
    # ohne Sicherheitsfrage ist nur der Admin-Reset möglich.
    sicherheitsfrage: str = Field("", max_length=200)
    sicherheitsantwort: str = Field("", max_length=200)


class BenutzerUpdate(BaseModel):
    anzeigename: Optional[str] = Field(None, max_length=150)
    rolle: Optional[str] = None
    aktiv: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6, max_length=200)
    sicherheitsfrage: Optional[str] = Field(None, max_length=200)
    sicherheitsantwort: Optional[str] = Field(None, max_length=200)


class BenutzerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    username: str
    anzeigename: str
    rolle: str
    aktiv: bool
    # Nur ob eine Sicherheitsfrage hinterlegt ist, NIE die Antwort selbst.
    hat_sicherheitsfrage: bool = False
    created_at: datetime
    updated_at: datetime


class PasswortVergessenRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)


class PasswortVergessenResponse(BaseModel):
    """Liefert NUR die hinterlegte Sicherheitsfrage zurück (nie, ob der
    Benutzername existiert - siehe routers/auth.py, verhindert
    Benutzernamen-Enumeration)."""
    sicherheitsfrage: Optional[str] = None


class PasswortResetRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    sicherheitsantwort: str = Field(..., min_length=1, max_length=200)
    neues_passwort: str = Field(..., min_length=6, max_length=200)


class LoginResponse(BaseModel):
    role: str
    username: str
    anzeigename: str = ""


# --- Personal-Stammdaten ---------------------------------------------------


class MitarbeiterBase(BaseModel):
    vorname: str = Field(..., min_length=1, max_length=100)
    nachname: str = Field(..., min_length=1, max_length=100)
    personalnummer: str = Field("", max_length=50)
    funktion: str = Field("", max_length=100)
    email: str = Field("", max_length=150)
    telefon: str = Field("", max_length=50)
    aktiv: bool = True
    notizen: str = Field("", max_length=1000)


class MitarbeiterCreate(MitarbeiterBase):
    pass


class MitarbeiterUpdate(MitarbeiterBase):
    pass


class MitarbeiterOut(MitarbeiterBase):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    # Weich gelöscht (siehe models.py:Mitarbeiter.geloescht und
    # routers/mitarbeiter.py: delete_mitarbeiter/restore_mitarbeiter) -
    # bleibt in der Datenbank erhalten und ist standardmäßig in Listen
    # ausgeblendet (siehe GET /api/mitarbeiter ?mit_geloeschten=true).
    geloescht: bool = False
    geloescht_am: Optional[datetime] = None
    geloescht_durch: str = ""
    created_at: datetime
    updated_at: datetime


class MitarbeiterDuplikatGruppe(BaseModel):
    """Eine Gruppe vermutlich doppelt angelegter Mitarbeiter-Stammdatensätze
    (exakt gleicher Name ODER sehr ähnlicher Name/Tippfehler, siehe
    mitarbeiter_duplikate.py). Rein informativ - der Admin/Disponent
    entscheidet selbst, welcher Datensatz bleibt (siehe
    routers/mitarbeiter.py: delete_mitarbeiter für den Rest)."""

    grund: str  # "exakt" oder "aehnlich"
    mitarbeiter: list[MitarbeiterOut]


# --- Dienstplan -------------------------------------------------------------


class DienstplanEintragOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    datum: date
    mitarbeiter_name: str
    mitarbeiter_id: Optional[Union[int, str]] = None
    dienst_kategorie: Optional[str] = None
    start_zeit: Optional[str] = None
    end_zeit: Optional[str] = None
    ist_krank: bool = False
    ist_bulmorfahrer: bool = False
    # Manuell aus der Tag/Nacht/Dispo-Gesamtrechnung herausgenommen, siehe
    # models.py:DienstplanEintrag.ausgeschlossen.
    ausgeschlossen: bool = False
    # Manuell aus dem Dienstplan entfernt (weich gelöscht, siehe
    # routers/dienstplan.py: delete_dienstplan_eintrag). Bleibt in der
    # Datenbank erhalten und kann über restore_dienstplan_eintrag
    # wiederhergestellt werden; standardmäßig in Listen ausgeblendet
    # (siehe GET /api/dienstplan ?mit_geloeschten=true).
    geloescht: bool = False
    geloescht_am: Optional[datetime] = None
    geloescht_durch: str = ""
    wiederhergestellt_am: Optional[datetime] = None
    wiederhergestellt_durch: str = ""
    # True = nicht aus einem Excel-Import, sondern manuell über
    # POST /api/dienstplan hinzugefügt (siehe create_dienstplan_eintrag).
    manuell_hinzugefuegt: bool = False
    hinzugefuegt_durch: str = ""
    # Nachträglich erfasste Verspätung in Minuten, siehe
    # models.py:DienstplanEintrag.verspaetung_minuten ("Ver."-Popup im
    # Frontend). Ergänzt start_zeit, überschreibt sie nicht.
    verspaetung_minuten: int = 0
    # Wer/wann die aktuelle Verspätung zuletzt erfasst hat, siehe
    # models.py:DienstplanEintrag.verspaetung_erfasst_von/_am.
    verspaetung_erfasst_von: str = ""
    verspaetung_erfasst_am: Optional[datetime] = None
    notiz: str = ""
    quelle_datei: str = ""
    created_at: datetime
    # True = kein echter Dienstplan-Eintrag, sondern aus einer laufenden
    # Krankmeldung abgeleitet (Tag noch nicht aus Excel importiert). Nur
    # lesbar, siehe routers/dienstplan.py (_virtuelle_krank_eintraege).
    virtuell: bool = False
    # Serverseitig berechnet (siehe dienstplan_sortierung.py), nicht gespeichert:
    effektive_kategorie: Optional[str] = None
    sortier_rang: int = 999
    ist_dispo: bool = False
    zeit_abweichend: bool = False
    schicht_typ: Optional[str] = None


class DienstplanEintragCreate(BaseModel):
    """Manuelles Hinzufügen einer einzelnen Person zu einem Tagesdienstplan
    (unabhängig von einem Excel-Import), siehe
    routers/dienstplan.py:create_dienstplan_eintrag."""

    datum: date
    mitarbeiter_name: str = Field(..., min_length=1, max_length=150)
    mitarbeiter_id: Optional[Union[int, str]] = None
    dienst_kategorie: Optional[str] = Field(None, max_length=20)
    start_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    ist_krank: bool = False
    ist_bulmorfahrer: bool = False
    notiz: str = Field("", max_length=500)


class DienstplanEintragUpdate(BaseModel):
    ist_krank: Optional[bool] = None
    ist_bulmorfahrer: Optional[bool] = None
    ausgeschlossen: Optional[bool] = None
    start_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    # Verspätung in Minuten, siehe models.py:DienstplanEintrag.verspaetung_minuten
    # und das "Ver."-Popup im Frontend (Schnellwahl 5-Minuten-Schritte bis
    # 60 Minuten + manuelle Eingabe). Obergrenze ist nur eine grobe
    # Plausibilitätsgrenze (12 Stunden), keine fachliche Begrenzung.
    verspaetung_minuten: Optional[int] = Field(None, ge=0, le=720)
    notiz: Optional[str] = Field(None, max_length=500)
    # Nur relevant, wenn ist_krank von true auf false wechselt: löscht dann
    # zusätzlich die passende(n) laufende(n) Krankmeldung(en) dieser Person
    # für diesen Tag (siehe routers/dienstplan.py). Fließt NICHT in die
    # eigentliche Dienstplan-Aktualisierung ein (exclude_unset/exclude_none).
    auch_krankmeldung_loeschen: Optional[bool] = None


class DienstplanQuelle(BaseModel):
    datum: date
    quelle_datei: Optional[str] = None
    importiert_am: Optional[datetime] = None
    anzahl_eintraege: int = 0


class DienstplanAuswertungZeile(BaseModel):
    """Eine Zeile der Verspätungs-Zusammenfassung je Mitarbeiter:in
    (siehe routers/dienstplan.py: GET /api/dienstplan/auswertung)."""

    mitarbeiter_name: str
    anzahl_verspaetungen: int
    summe_verspaetung_minuten: int


class VerspaetungsEintrag(BaseModel):
    """Einzelner erfasster Verspätungs-Vorfall (ein Dienstplan-Eintrag mit
    verspaetung_minuten > 0) - Detailzeile der Auswertung."""

    model_config = ConfigDict(from_attributes=True)

    dienstplan_id: Union[int, str]
    datum: date
    mitarbeiter_name: str
    dienst_kategorie: Optional[str] = None
    geplanter_beginn: Optional[str] = None
    verspaetung_minuten: int
    erfasst_von: str = ""
    erfasst_am: Optional[datetime] = None


class KrankmeldungsEintrag(BaseModel):
    """Einzelne Krankmeldung, deren Zeitraum sich mit dem Auswertungs-
    zeitraum überschneidet - Detailzeile der Auswertung."""

    report_id: Union[int, str]
    mitarbeiter_name: str
    sick_from: date
    sick_to: date
    kranktage: int
    accepted_by: str = ""
    reported_at: date


class KrankmeldungsZusammenfassung(BaseModel):
    mitarbeiter_name: str
    anzahl_krankmeldungen: int
    kranktage_gesamt: int


class DienstplanAuswertungOut(BaseModel):
    """Komplette Dienstplan-Auswertung für einen Zeitraum (siehe
    routers/dienstplan.py: GET /api/dienstplan/auswertung) - Verspätungen
    UND Krankmeldungen, jeweils als Einzel-Vorfälle und als Zusammenfassung
    je Mitarbeiter:in, für den Tab "Dienstplan Auswertung" im Frontend."""

    von: date
    bis: date
    verspaetungen: list[VerspaetungsEintrag]
    verspaetungen_zusammenfassung: list[DienstplanAuswertungZeile]
    krankmeldungen: list[KrankmeldungsEintrag]
    krankmeldungen_zusammenfassung: list[KrankmeldungsZusammenfassung]


class DienstplanAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    event_at: datetime
    dienstplan_id: Optional[Union[int, str]] = None
    # Betroffener Dienstplan-Tag (siehe models.py:DienstplanAudit.datum) -
    # kann von event_at.date() abweichen (z. B. nachträgliche Korrektur
    # eines älteren Tages).
    datum: Optional[date] = None
    mitarbeiter_name: str = ""
    action: str
    actor_role: str
    actor_username: str = ""
    old_data: Optional[dict] = None
    new_data: Optional[dict] = None


class KrankOhneMeldung(BaseModel):
    """Dienstplan-Eintrag, der als 'Krank' erkannt wurde, aber (noch) keine
    passende Krankmeldung für diesen Tag hat (siehe routers/dienstplan.py,
    _krank_ohne_meldung)."""
    mitarbeiter_name: str
    datum: date


class UnsichereZuordnung(BaseModel):
    """Dienstplan-Name, der beim Import nur unscharf (Tippfehler/Dreher)
    oder gar nicht eindeutig einem Stammdatensatz zugeordnet werden konnte
    (siehe mitarbeiter_matching.py) - zur manuellen Prüfung.

    Die automatische Zuordnung wurde dabei bereits auf den Dienstplan-
    Eintrag (eintrag_id) übernommen (siehe routers/dienstplan.py:
    import_dienstplan) - über /api/dienstplan/{eintrag_id}/zuordnung/
    bestaetigen bzw. .../ablehnen kann sie im Frontend bestätigt oder
    rückgängig gemacht werden (dann mitarbeiter_id=None, wie bei einer
    'nicht zugeordneten' Person)."""
    mitarbeiter_name: str
    vorname: str = ""
    nachname: str = ""
    vorschlag: Optional[str] = None  # Name des unsicher erkannten Treffers, falls vorhanden
    eintrag_id: Optional[Union[int, str]] = None
    vorgeschlagene_mitarbeiter_id: Optional[Union[int, str]] = None


class NichtZugeordneterMitarbeiter(BaseModel):
    """Name aus dem Dienstplan-Import, der KEINEM Stammdatensatz zugeordnet
    werden konnte (siehe mitarbeiter_matching.ordne_mitarbeiter_zu) - der
    Dienstplan-Eintrag wurde trotzdem angelegt (mitarbeiter_id=None).
    vorname/nachname stammen direkt aus der Excel-Zelle (siehe
    dienstplan_parser.py) und dienen als Vorbelegung für das Formular
    "Mitarbeiter:in anlegen" im Frontend."""
    mitarbeiter_name: str
    vorname: str = ""
    nachname: str = ""
    eintrag_id: Optional[Union[int, str]] = None


class DienstplanImportResult(BaseModel):
    success: bool
    datum: Optional[date] = None
    anzahl_eintraege: int = 0
    anzahl_krank: int = 0
    anzahl_bulmorfahrer: int = 0
    unbekannte_dienste: list[str] = []
    krank_ohne_meldung: list[KrankOhneMeldung] = []
    nicht_zugeordnete_mitarbeiter: list[NichtZugeordneterMitarbeiter] = []
    unsichere_zuordnungen: list[UnsichereZuordnung] = []
    error: Optional[str] = None


# --- Meldungen (allgemeines Mitteilungsboard) -------------------------------


class MeldungBase(BaseModel):
    titel: str = Field(..., min_length=1, max_length=200)
    text: str = Field("", max_length=4000)
    angeheftet: bool = False


class MeldungCreate(MeldungBase):
    pass


class MeldungUpdate(MeldungBase):
    pass


class MeldungOut(MeldungBase):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    autor: str
    created_at: datetime
    updated_at: datetime


# --- Mitarbeiter-Historie ----------------------------------------------------


class MitarbeiterEreignisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    event_at: datetime
    mitarbeiter_id: Optional[Union[int, str]] = None
    mitarbeiter_name: str = ""
    ereignis_typ: str
    beschreibung: str = ""
    bezug_typ: Optional[str] = None
    bezug_id: Optional[str] = None
    actor_username: str = ""
    actor_role: str = ""
    details: Optional[dict] = None


class MitarbeiterHistorieOut(BaseModel):
    """Historie eines einzelnen Mitarbeiters: Chronologie + verdichtete
    Kennzahlen (siehe routers/mitarbeiter.py:get_mitarbeiter_historie)."""

    mitarbeiter_id: Union[int, str]
    anzahl_krankmeldungen: int = 0
    anzahl_krank_tage_gesamt: int = 0
    letzte_krankmeldung_von: Optional[date] = None
    letzte_krankmeldung_bis: Optional[date] = None
    ereignisse: list[MitarbeiterEreignisOut] = []


# --- Benutzer-Aktivitätsprotokoll (Logfile je Account) ----------------------


class BenutzerAktivitaetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    event_at: datetime
    username: str = ""
    rolle: str = ""
    aktion: str
    bereich: str = ""
    entity_typ: Optional[str] = None
    entity_id: Optional[str] = None
    entity_bezeichnung: str = ""
    beschreibung: str = ""
    details: Optional[dict] = None
