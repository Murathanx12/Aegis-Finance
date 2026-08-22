Set-Location C:\Users\mrthn\aegis-finance
$log = "C:\Users\mrthn\aegis-finance\backend\data\optimus\wrds\jkp_full\pull_foreign.log"
for ($i = 1; $i -le 20; $i++) {
    "=== foreign invocation $i $(Get-Date -Format o) ===" | Add-Content $log
    python -m scripts.wrds_pull_jkp_full --foreign-only --max-seconds 100000 2>&1 |
        Add-Content $log
    if ((Get-Content $log -Tail 5) -match "ALL \d+ foreign subset on disk") {
        "FOREIGN DONE $(Get-Date -Format o)" | Add-Content $log
        break
    }
    Start-Sleep -Seconds 30
}
