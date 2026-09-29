@echo off
rem nn_lab nightly loop. Scheduled task "AegisNNLabNightly" (08:30 HKT, after the 06:30 HKT bars refresh).
rem Stop: create backend\data\optimus\nn_lab\STOP.  Remove: schtasks /Delete /TN "AegisNNLabNightly" /F
cd /d "%~dp0.."
set AEGIS_IGNORE_DOTENV=1
if not exist "backend\data\optimus\local_pc\nn_lab" mkdir "backend\data\optimus\local_pc\nn_lab"
"nn_lab\.venv\Scripts\python.exe" -m nn_lab.nightly >> "backend\data\optimus\local_pc\nn_lab\nightly.log" 2>&1
