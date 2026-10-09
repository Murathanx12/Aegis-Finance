@echo off
rem 2026-10-02: %1 = --until HH:MM (rolling, from scripts.task_keeper reader), %2 = dated log.
rem With no arguments it behaves as before (until 12:00, the 09-29 log).
rem Pause: create backend/data/optimus/dowjones/SUPERVISOR_STOP (the keeper will not relaunch it).
cd /d C:\Users\mrthn\aegis-finance
set "UNTIL=%~1"
if "%UNTIL%"=="" set "UNTIL=12:00"
set "SUPLOG=%~2"
if "%SUPLOG%"=="" set "SUPLOG=backend\data\optimus\dowjones\supervisor_2026-09-29.log"
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.night_reader_supervisor --until %UNTIL% < backend\data\optimus\empty_stdin.txt >> "%SUPLOG%" 2>&1
