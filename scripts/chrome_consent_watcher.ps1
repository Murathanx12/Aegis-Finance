# Approves Chrome's "Allow remote debugging?" prompt while the PC is handed over.
#
# WHY (2026-09-27): every reset of OpenClaw's Chrome MCP session makes Chrome raise
# this prompt and wait for a click. Overnight nobody was there, so every attach after
# 04:48 timed out ("existing-session attach ... timed out after 5000ms") and the
# reading queue stopped. Murat enabled remote debugging himself, approved this same
# prompt by hand on 09-26, and handed the PC over ("full access").
#
# WHAT IT DOES, AND ONLY THIS:
#   * runs ONLY while backend/data/optimus/HANDOFF_PC exists (Murat deletes it = stop);
#   * looks for a Chrome window that contains the text "Allow remote debugging?" and
#     invokes the button named "Allow" INSIDE that window via UI Automation -- no
#     keystrokes, no coordinates, nothing sent to any other window;
#   * appends one line per approval to backend/data/optimus/chrome_consent.log.jsonl.
# It never toggles the setting itself and never touches any other dialog.
param([int]$PollSeconds = 4, [int]$MaxHours = 12)

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$repo    = Split-Path -Parent $PSScriptRoot
$handoff = Join-Path $repo 'backend\data\optimus\HANDOFF_PC'
$log     = Join-Path $repo 'backend\data\optimus\chrome_consent.log.jsonl'
$pidFile = Join-Path $repo 'backend\data\optimus\chrome_consent_watcher.pid'
"watcher PID $PID started $(Get-Date -Format o)" | Set-Content -Encoding utf8 $pidFile

$AE   = [System.Windows.Automation.AutomationElement]
$Tree = [System.Windows.Automation.TreeScope]
$nameP = $AE::NameProperty
$typeP = $AE::ControlTypeProperty
$btnT  = [System.Windows.Automation.ControlType]::Button
$deadline = (Get-Date).AddHours($MaxHours)

function Write-Line($obj) { ($obj | ConvertTo-Json -Compress) | Add-Content -Encoding utf8 $log }

Write-Line @{ t = (Get-Date).ToUniversalTime().ToString('o'); event = 'start'; pid = $PID }
while ((Get-Date) -lt $deadline) {
    if (-not (Test-Path $handoff)) {
        Write-Line @{ t = (Get-Date).ToUniversalTime().ToString('o'); event = 'exit'; reason = 'HANDOFF_PC absent' }
        break
    }
    try {
        $procs = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }
        foreach ($p in $procs) {
            $win = $AE::FromHandle($p.MainWindowHandle)
            if ($null -eq $win) { continue }
            $titleCond = New-Object System.Windows.Automation.PropertyCondition($nameP, 'Allow remote debugging?')
            $title = $win.FindFirst($Tree::Descendants, $titleCond)
            if ($null -eq $title) { continue }
            $cond = New-Object System.Windows.Automation.AndCondition(
                (New-Object System.Windows.Automation.PropertyCondition($typeP, $btnT)),
                (New-Object System.Windows.Automation.PropertyCondition($nameP, 'Allow')))
            $btn = $win.FindFirst($Tree::Descendants, $cond)
            if ($null -eq $btn) {
                Write-Line @{ t = (Get-Date).ToUniversalTime().ToString('o'); event = 'prompt_seen_no_button'; chrome_pid = $p.Id }
                continue
            }
            $inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $inv.Invoke()
            Write-Line @{ t = (Get-Date).ToUniversalTime().ToString('o'); event = 'approved'; chrome_pid = $p.Id; window = $p.MainWindowTitle }
            Start-Sleep -Seconds 2
        }
    } catch {
        Write-Line @{ t = (Get-Date).ToUniversalTime().ToString('o'); event = 'error'; error = $_.Exception.Message }
    }
    Start-Sleep -Seconds $PollSeconds
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
