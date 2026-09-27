@echo off
rem Opens a SEPARATE Chrome instance for MuratClaw, with its own data folder.
rem OpenClaw attaches to THIS instance only; Murat's main Chrome is never touched.
rem First run: sign in to Google, then WSJ / Barron's / MarketWatch, then open
rem   chrome://inspect/#remote-debugging   and tick "Allow remote debugging".
rem In the MAIN Chrome, untick that same box so nothing can attach to it.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\Users\mrthn\ChromeMuratClaw" --no-first-run https://www.wsj.com/
