@echo off
cd /d C:\Users\mrthn\aegis-finance
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.official_sources --source sec_form4 --source finra_sv >> backend\data\optimus\official\official_sources.log 2>&1
