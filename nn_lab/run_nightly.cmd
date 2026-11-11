@echo off
rem nn_lab nightly loop. Scheduled task "AegisNNLabNightly" (08:30 HKT, after the 06:30 HKT bars refresh).
rem Stop: create backend\data\optimus\nn_lab\STOP.  Remove: schtasks /Delete /TN "AegisNNLabNightly" /F
rem CH-05 (2026-11-11): delegates to the runtime wrapper. The interpreter comes from
rem scripts\runtime_task.config (AEGIS_NN_LAB_VENV_DIR), not "nn_lab\.venv" relative to this file
rem (a release clone has no venv of its own), and the wrapper refuses to run when this checkout's
rem backend\data\optimus is not the live data. The task action calls the wrapper directly
rem (scripts\runtime_release.py prints it); this file stays for a human at a console.
call "%~dp0..\scripts\runtime_task.cmd" --nn-lab --set AEGIS_IGNORE_DOTENV=1 --log backend\data\optimus\local_pc\nn_lab\nightly.log -m nn_lab.nightly
exit /b %ERRORLEVEL%
