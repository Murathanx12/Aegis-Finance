@echo off
cd /d C:\Users\mrthn\aegis-finance
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.dowjones_pull --queue backend\data\optimus\dowjones\QUEUE_2026-09-27_wide.txt --handoff --profile muratclaw --workers 3 < backend\data\optimus\empty_stdin.txt >> backend\data\optimus\dowjones\queue_run_2026-09-28b.log 2>> backend\data\optimus\dowjones\queue_run_2026-09-28b.log.err
