$ErrorActionPreference = 'SilentlyContinue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$startVbs = Join-Path $rootDir "start.vbs"

Write-Host "[Restart] Project: $rootDir"

# 终止 ChallengeDaily Electron 进程
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

# 终止项目相关的 Python 后端进程（避免旧代码残留）
$allPy = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"
$pyToKill = @()
foreach ($p in $allPy) {
    if ($p.CommandLine -and ($p.CommandLine -like "*$rootDir*")) {
        $pyToKill += $p
    }
}
if ($pyToKill.Count -gt 0) {
    Write-Host "[Restart] Found $($pyToKill.Count) project Python process(es), stopping..."
    foreach ($p in $pyToKill) {
        Stop-Process -Id $p.ProcessId -Force
    }
    Start-Sleep -Seconds 1
    Write-Host "[Restart] Python process(es) stopped"
}

if (Test-Path $startVbs) {
    Write-Host "[Restart] Starting $startVbs"
    Start-Process $startVbs
} else {
    Write-Error "[Restart] Start script not found: $startVbs"
}
