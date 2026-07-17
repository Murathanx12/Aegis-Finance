@echo off
REM ── Aegis Finance one-click local launcher ─────────────────────────────
REM Double-click to run the full stack locally: backend (FastAPI :8000),
REM frontend (Next.js :3000), then opens the browser.
REM
REM Why this instead of an .exe: Aegis is a hosted web app (Railway +
REM Vercel) — users just visit the URL. Bundling the backend with
REM PyInstaller would ship ~2 GB of torch/LightGBM and break on every
REM dependency bump; this launcher gives the same one-click experience
REM for local runs without any of that. Requires: Python 3.12 + deps
REM installed (pip install -r backend/requirements.txt), npm install done
REM once in frontend/.

cd /d "%~dp0"

echo Starting Aegis backend on http://localhost:8000 ...
start "aegis-backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --port 8000"

echo Starting Aegis frontend on http://localhost:3000 ...
start "aegis-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Waiting for servers to come up...
timeout /t 10 /nobreak >nul

start http://localhost:3000

echo.
echo Aegis is starting in two terminal windows. Close them to stop.
echo (First backend boot takes ~1 min while caches prewarm.)
pause
