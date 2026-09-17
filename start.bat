@echo off
rem WLAN Finder starten - zum Doppelklicken oder als Desktop-Verknuepfung.
rem
rem %~dp0 ist der Ordner, in dem diese Datei liegt. Dadurch funktioniert der
rem Start unabhaengig davon, von wo aus er aufgerufen wird - auch von einer
rem Verknuepfung auf dem Desktop.
cd /d "%~dp0"

rem Optional: API-Key fuer den Portal-Agenten. Ist er hier gesetzt oder als
rem Systemvariable ANTHROPIC_API_KEY vorhanden, kann sich WLAN Finder an
rem Captive Portals anmelden. Ohne ihn laeuft alles andere trotzdem.
rem set ANTHROPIC_API_KEY=sk-ant-...

py -m wlanfinder
if errorlevel 1 (
    echo.
    echo WLAN Finder wurde beendet oder konnte nicht starten.
    pause
)
