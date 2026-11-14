@echo off
setlocal
set "TOOL_DIR=%~dp0Verwaltungstool"
set "VENV_DIR=%LOCALAPPDATA%\DRKFKB-Krankmeldungen\venv-verwaltungstool"

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
echo [Hinweis] Die Webapp muss bereits laufen (siehe start_app.bat), sonst
echo [Hinweis] kann sich dieses Tool nicht anmelden.
echo.
echo [Start] Verwaltungstool wird geoeffnet ...
"%VENV_DIR%\Scripts\python.exe" gui.py

endlocal
