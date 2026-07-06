$ErrorActionPreference = 'SilentlyContinue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$startVbs = Join-Path $rootDir "start.vbs"

Write-Host "[Restart] Project: $rootDir"

$targetProcesses = Get-Process | Where-Object {
    $_.Path -and ($_.Path -like "*$rootDir*electron.exe*")
}

if ($targetProcesses) {
    $count = ($targetProcesses | Measure-Object).Count
    Write-Host "[Restart] Found $count ChallengeDaily process(es), stopping..."
    $targetProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "[Restart] Old process(es) stopped"
} else {
    Write-Host "[Restart] No running ChallengeDaily process found"
}

if (Test-Path $startVbs) {
    Write-Host "[Restart] Starting $startVbs"
    Start-Process $startVbs
} else {
    Write-Error "[Restart] Start script not found: $startVbs"
}
