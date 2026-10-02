@echo off
set AEGIS_PERSONAL_MODE=0
cd /d C:\Users\mrthn\aegis-finance
set P=.venv\Scripts\python.exe -m scripts.hyp_llm_theories run --run r1 --provider local --workers 2
%P% --q q1 --arm text
if exist backend\data\optimus\hyp_lab\job3_r1\STOP exit /b 3
%P% --q q2 --arm text
if exist backend\data\optimus\hyp_lab\job3_r1\STOP exit /b 3
%P% --q id --arm text --limit 120
if exist backend\data\optimus\hyp_lab\job3_r1\STOP exit /b 3
%P% --q q1 --arm text --split val
if exist backend\data\optimus\hyp_lab\job3_r1\STOP exit /b 3
%P% --q q1 --arm num --limit 120
echo CHAIN_DONE
