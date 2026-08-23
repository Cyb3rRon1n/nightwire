param(
  [switch]$IncludeOllama
)

$ErrorActionPreference = "Stop"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Repo

function Write-Step($Message) {
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-PortListeners($Port, $Name) {
  if (-not (Get-Command "Get-NetTCPConnection" -ErrorAction SilentlyContinue)) {
    throw "Get-NetTCPConnection is not available on this Windows install."
  }

  $connections = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  )
  $processIds = @(
    $connections |
      Select-Object -ExpandProperty OwningProcess -Unique |
      Where-Object { $_ -and $_ -gt 0 }
  )

  if (-not $processIds.Count) {
    Write-Host "$Name is not listening on port $Port."
    return
  }

  foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
      continue
    }

    Write-Host "Stopping $Name on port ${Port}: $($process.ProcessName) ($processId)"
    Stop-Process -Id $processId -Force
  }
}

Write-Step "Stopping Open Dungeon"
Stop-PortListeners 3000 "Open Dungeon web app"
Stop-PortListeners 7869 "Open Dungeon image worker"

if ($IncludeOllama) {
  Write-Step "Stopping Ollama"
  $ollamaProcesses = @(Get-Process -Name "ollama" -ErrorAction SilentlyContinue)
  if (-not $ollamaProcesses.Count) {
    Write-Host "Ollama is not running."
  }
  foreach ($process in $ollamaProcesses) {
    Write-Host "Stopping Ollama: $($process.ProcessName) ($($process.Id))"
    Stop-Process -Id $process.Id -Force
  }
} else {
  Write-Host ""
  Write-Host "Ollama was left running. Run scripts\stop-windows.ps1 -IncludeOllama if you want to stop it too."
}

Write-Host ""
Write-Host "Open Dungeon stop complete." -ForegroundColor Green
