@echo off
cd /d C:\Users\mrthn\aegis-finance
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.official_sources --backfill-form4 7 >> backend\data\optimus\official\backfill_form4.log 2>&1
