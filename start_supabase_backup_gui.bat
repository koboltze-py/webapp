@echo off
setlocal
set "TOOL_DIR=%~dp0Supabase-Sicherung"
set "VENV_DIR=%LOCALAPPDATA%\DRKFKB-Krankmeldungen\venv-backup-gui"

rem Siehe start_app.bat: venv bewusst ausserhalb von OneDrive (Pfadlaenge).

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [Setup] Erstelle virtuelle Python-Umgebung unter %VENV_DIR% ...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 python -m venv "%VENV_DIR%"
)

cd /d "%TOOL_DIR%"

echo [Setup] Pruefe/Installiere Abhaengigkeiten ...
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet -r requirements.txt

echo.
echo [Start] Supabase-Sicherungs-GUI wird geoeffnet ...
"%VENV_DIR%\Scripts\python.exe" backup_gui.py

endlocal
