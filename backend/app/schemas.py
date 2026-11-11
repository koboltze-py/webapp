"""Pydantic-Schemas für Request/Response der API."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

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

    id: int
    created_at: datetime
    updated_at: datetime


class CaremanUpdate(BaseModel):
    careman_done: bool


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_at: datetime
    report_id: Optional[int]
    action: str
    actor_role: str
    old_data: Optional[dict]
    new_data: Optional[dict]
