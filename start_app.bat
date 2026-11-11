@echo off
setlocal
set "BACKEND_DIR=%~dp0backend"
set "VENV_DIR=%LOCALAPPDATA%\DRKFKB-Krankmeldungen\venv-backend"

rem Die virtuelle Umgebung liegt bewusst AUSSERHALB von OneDrive:
rem In sehr langen OneDrive-Pfaden (wie diesem) scheitert die
rem Python-Installation von pip an der Windows-Pfadlaengenbegrenzung.
rem Zudem muss .venv nicht synchronisiert werden (nur Bibliotheken).

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [Setup] Erstelle virtuelle Python-Umgebung unter %VENV_DIR% ...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 python -m venv "%VENV_DIR%"
)

cd /d "%BACKEND_DIR%"

echo [Setup] Pruefe/Installiere Abhaengigkeiten ...
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet -r requirements.txt

echo.
echo [Start] DRK FKB Krankmeldungen wird gestartet unter http://127.0.0.1:8000
echo [Hinweis] Dieses Fenster offen lassen, solange die Webapp genutzt wird.
echo [Hinweis] Fenster schliessen oder STRG+C druecken, um den Server zu stoppen.
echo.

start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8000"
"%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

endlocal
