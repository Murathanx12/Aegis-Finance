@echo off
cd /d "C:\Users\mrthn\aegis-finance"
set AEGIS_PERSONAL_MODE=0
"C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe" -m scripts.hyp_lab nightly --k 3 --cap 0.4 >> "C:\Users\mrthn\aegis-finance\backend\data\optimus\hyp_lab\nightly.log" 2>&1
