@echo off
rem CH-05 wrapper, console entry. Same logic as the scheduled-task entry:
rem   <venv>\Scripts\pythonw.exe -I <clone>\scripts\runtime_task.py [options] -m <module> [args...]
rem The logic lives in runtime_task.py (see its docstring); this file only finds the venv
rem interpreter (environment first, then runtime_task.config) and returns the exit code unchanged.
rem A task action should NOT point here: a .cmd action opens a console window for the whole run.
setlocal EnableExtensions DisableDelayedExpansion
if not defined AEGIS_VENV_DIR (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0runtime_task.config") do (
    if /i "%%A"=="AEGIS_VENV_DIR" set "AEGIS_VENV_DIR=%%B"
  )
)
if not defined AEGIS_VENV_DIR (
  echo runtime_task REFUSED: AEGIS_VENV_DIR is not configured 1>&2
  exit /b 90
)
if not exist "%AEGIS_VENV_DIR%\Scripts\python.exe" (
  echo runtime_task REFUSED: no interpreter at %AEGIS_VENV_DIR%\Scripts\python.exe 1>&2
  exit /b 90
)
"%AEGIS_VENV_DIR%\Scripts\python.exe" -I "%~dp0runtime_task.py" %*
exit /b %ERRORLEVEL%
