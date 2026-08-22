#: detached loop for scripts/wrds_pull_jkp_full.py — restarts on transient
#: failures (connection drops), stops when every chunk is on disk.
Set-Location C:\Users\mrthn\aegis-finance
$log = "C:\Users\mrthn\aegis-finance\backend\data\optimus\wrds\jkp_full\pull_loop.log"
for ($i = 1; $i -le 50; $i++) {
    "=== invocation $i $(Get-Date -Format o) ===" | Add-Content $log
    python -m scripts.wrds_pull_jkp_full --max-seconds 100000 2>&1 |
        Add-Content $log
    if ((Get-Content $log -Tail 5) -match "ALL \d+ chunks on disk") {
        "DONE $(Get-Date -Format o)" | Add-Content $log
        break
    }
    Start-Sleep -Seconds 30
}
