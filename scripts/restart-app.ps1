$ErrorActionPreference = 'SilentlyContinue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$startVbs = Join-Path $rootDir "start.vbs"
$backendPort = 58888

Write-Host "[Restart] Project: $rootDir"

# Kill Electron / ChallengeDaily processes by name
$electronProcs = Get-Process -Name "electron" -ErrorAction SilentlyContinue
$challengeProcs = Get-Process -Name "ChallengeDaily" -ErrorAction SilentlyContinue
$targetProcesses = @($electronProcs) + @($challengeProcs) | Where-Object { $_ -ne $null }

if ($targetProcesses.Count -gt 0) {
    Write-Host "[Restart] Found $($targetProcesses.Count) Electron/ChallengeDaily process(es), stopping..."
    $targetProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "[Restart] Electron process(es) stopped"
} else {
    Write-Host "[Restart] No running Electron process found"
}

# Kill project-related Python backend processes
$allPy = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"
$pyToKill = @()
foreach ($p in $allPy) {
    if ($p.CommandLine -and ($p.CommandLine -like "*xiaohei-daily*")) {
        $pyToKill += $p
    }
}
if ($pyToKill.Count -gt 0) {
    Write-Host "[Restart] Found $($pyToKill.Count) project Python process(es), stopping..."
    foreach ($p in $pyToKill) {
        $cmdShort = $p.CommandLine
        if ($cmdShort.Length -gt 80) { $cmdShort = $cmdShort.Substring(0, 80) }
        Write-Host "[Restart]   Killing PID $($p.ProcessId): $cmdShort"
        Stop-Process -Id $p.ProcessId -Force
    }
    Start-Sleep -Seconds 2
    Write-Host "[Restart] Python process(es) stopped"
} else {
    Write-Host "[Restart] No project Python process found"
}

# Wait for backend port to be released
$portWaitSec = 0
$maxPortWait = 10
while ($portWaitSec -lt $maxPortWait) {
    $portInUse = (netstat -ano | Select-String ":$backendPort.*LISTENING")
    if (-not $portInUse) {
        Write-Host "[Restart] Port $backendPort is free"
        break
    }
    Write-Host "[Restart] Waiting for port $backendPort to release ($portWaitSec / $maxPortWait s)..."
    Start-Sleep -Seconds 1
    $portWaitSec++
}

if ($portWaitSec -ge $maxPortWait) {
    Write-Host "[Restart] WARNING: Port $backendPort still in use after $maxPortWait s, proceeding anyway"
}

# Start the application
if (Test-Path $startVbs) {
    Write-Host "[Restart] Starting $startVbs"
    Start-Process $startVbs
} else {
    Write-Error "[Restart] Start script not found: $startVbs"
}
