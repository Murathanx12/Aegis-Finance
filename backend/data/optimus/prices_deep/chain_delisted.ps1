param($py,$repo,$dir)
# wait for the survivor pull to finish, then pull the DEAD names on the same
# credential. Sequential on purpose: two concurrent paginated pulls invite a
# 429 storm that would fail both.
while (Get-Process -Id 65272 -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 20 }
Start-Sleep -Seconds 5
& $py -m scripts.pull_delisted_bars --start 2016-01-01 *> "$dir\delisted.log"
