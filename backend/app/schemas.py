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
    dienst_kategorie: Optional[str] = None
    start_zeit: Optional[str] = None
    end_zeit: Optional[str] = None
    ist_krank: bool = False
    ist_bulmorfahrer: bool = False
    notiz: str = ""
    quelle_datei: str = ""
    created_at: datetime


class DienstplanImportResult(BaseModel):
    success: bool
    datum: Optional[date] = None
    anzahl_eintraege: int = 0
    anzahl_krank: int = 0
    anzahl_bulmorfahrer: int = 0
    unbekannte_dienste: list[str] = []
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
