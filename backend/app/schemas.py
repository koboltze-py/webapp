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

TIER_ROLES = ("mitarbeiter", "schichtleitung", "admin")


class BenutzerCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=6, max_length=200)
    anzeigename: str = Field("", max_length=150)
    rolle: str = Field("mitarbeiter")
    aktiv: bool = True


class BenutzerUpdate(BaseModel):
    anzeigename: Optional[str] = Field(None, max_length=150)
    rolle: Optional[str] = None
    aktiv: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6, max_length=200)


class BenutzerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    username: str
    anzeigename: str
    rolle: str
    aktiv: bool
    created_at: datetime
    updated_at: datetime


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
    created_at: datetime
    updated_at: datetime


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


class DienstplanEintragUpdate(BaseModel):
    ist_krank: Optional[bool] = None
    ist_bulmorfahrer: Optional[bool] = None
    ausgeschlossen: Optional[bool] = None
    start_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_zeit: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
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


class DienstplanAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Union[int, str]
    event_at: datetime
    dienstplan_id: Optional[Union[int, str]] = None
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
    (siehe mitarbeiter_matching.py) - zur manuellen Prüfung."""
    mitarbeiter_name: str
    vorschlag: Optional[str] = None  # Name des unsicher erkannten Treffers, falls vorhanden


class DienstplanImportResult(BaseModel):
    success: bool
    datum: Optional[date] = None
    anzahl_eintraege: int = 0
    anzahl_krank: int = 0
    anzahl_bulmorfahrer: int = 0
    unbekannte_dienste: list[str] = []
    krank_ohne_meldung: list[KrankOhneMeldung] = []
    nicht_zugeordnete_mitarbeiter: list[str] = []
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
