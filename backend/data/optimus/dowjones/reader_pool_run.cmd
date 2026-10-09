@echo off
cd /d C:\Users\mrthn\aegis-finance
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.reader_pool --handoff --profile muratclaw --until 10:27 < backend\data\optimus\empty_stdin.txt >> backend\data\optimus\dowjones\reader_pool_2026-10-09.log 2>> backend\data\optimus\dowjones\reader_pool_2026-10-09.log.err
