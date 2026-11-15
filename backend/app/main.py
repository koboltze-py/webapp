"""FastAPI-Hauptanwendung.

Dieser eine Prozess übernimmt sowohl das Backend (JSON-API unter /api/...)
als auch die Auslieferung der Webapp (frontend/index.html). Dadurch starten
Webapp und Backend immer gemeinsam mit einem einzigen Befehl
(siehe start_app.bat im Projektordner)."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, engine, run_startup_migrations
from .datensicherheit import finde_konfliktkopien, warnungen_text
from .routers import audit, auth, benutzer, dienstplan, meldungen, mitarbeiter, reports, system, wandanzeige

if not settings.supabase_enabled:
    Base.metadata.create_all(bind=engine)
    run_startup_migrations()
    # Siehe datensicherheit.py: macht OneDrive-Synchronisationskonflikte der
    # lokalen Datenbankdatei sichtbar (Ursache für scheinbar verschwindende
    # Dienstplan-Importe/Krankmeldungen), statt sie unbemerkt zu lassen.
    for warnung in warnungen_text(finde_konfliktkopien()):
        print(f"[WARNUNG] {warnung}")

app = FastAPI(title="DRK FKB Krankmeldungen", docs_url="/api/docs", redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="drkfkb_session",
    same_site="lax",
    max_age=settings.session_max_age_seconds,
)

app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(mitarbeiter.router)
app.include_router(dienstplan.router)
app.include_router(meldungen.router)
app.include_router(benutzer.router)
app.include_router(system.router)
app.include_router(wandanzeige.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
