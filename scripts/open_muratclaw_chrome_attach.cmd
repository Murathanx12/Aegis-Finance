@echo off
rem STEP 2 (after signing in once with open_muratclaw_chrome.cmd and CLOSING that window).
rem Reopens the SAME separate MuratClaw data folder with a local debugging port.
rem The port belongs to this instance only and listens on 127.0.0.1 only, so
rem OpenClaw can reach MuratClaw and cannot reach Murat's main Chrome at all.
rem No "Allow remote debugging?" prompt is involved, in either Chrome.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\Users\mrthn\ChromeMuratClaw" --remote-debugging-port=18802 --remote-debugging-address=127.0.0.1 --no-first-run https://www.wsj.com/
