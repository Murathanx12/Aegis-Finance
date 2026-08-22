# Detached runner for the panel-2 planted worlds (TOURNAMENT-2's gate).
#
# Launched with Start-Process so it outlives the session shell, which dies at
# ~10 minutes. One process holds the panel once for all three worlds; every
# (world, arm, fold) is cached, so a kill costs at most one fold.
#
# TWO PS 5.1 TRAPS, both paid for by the first attempt (which died silently
# after one line of output, with no traceback and no exit marker):
#   1. `2>&1` on a NATIVE exe wraps every stderr line in a NativeCommandError.
#      Python writes warnings to stderr, so the first pandas PerformanceWarning
#      became an "error".
#   2. With $ErrorActionPreference = "Stop", that fake error TERMINATED the
#      script mid-pipeline and killed the run.
# So: no ErrorActionPreference=Stop, no 2>&1 merge. Streams are separated by
# the process itself, which is where the separation belongs.
Set-Location "C:\Users\mrthn\aegis-finance"
$dir = "backend\data\optimus\aegis_panel"
$proc = Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList '-u', '-m', 'scripts.panel2_planted_worlds', '--world', 'all' `
    -RedirectStandardOutput "$dir\panel2_planted.log" `
    -RedirectStandardError  "$dir\panel2_planted.err" `
    -NoNewWindow -PassThru
$proc.WaitForExit()
"=== exit $($proc.ExitCode) at $(Get-Date -Format o) ===" |
    Out-File -FilePath "$dir\panel2_planted.done" -Encoding utf8
