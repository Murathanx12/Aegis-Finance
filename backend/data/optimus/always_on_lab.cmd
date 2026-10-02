@echo off
cd /d C:\Users\mrthn\aegis-finance
rem 2026-10-02: OFF means off. The persistent marker is honoured HERE (before
rem python starts) and again in scripts.always_on_lab main(). Delete
rem backend\data\optimus\always_on_lab_OFF to switch the lab back on.
if exist C:\Users\mrthn\aegis-finance\backend\data\optimus\always_on_lab_OFF (
  echo %DATE% %TIME% OFF: always_on_lab_OFF marker present, lab not started>> C:\Users\mrthn\aegis-finance\backend\data\optimus\always_on_lab.log
  exit /b 0
)
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.always_on_lab < C:\Users\mrthn\aegis-finance\backend\data\optimus\empty_stdin.txt >> C:\Users\mrthn\aegis-finance\backend\data\optimus\always_on_lab.log 2>&1
