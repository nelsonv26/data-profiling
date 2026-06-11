#Requires -Version 5.1
<#
.SYNOPSIS
    Uninstalls the data-profiling Helm release and removes its namespace.
#>

Write-Host ""
Write-Host "DataProfiler - Stopping..." -ForegroundColor Yellow
Write-Host "===========================" -ForegroundColor Yellow
Write-Host ""

# -- 1. Prerequisite checks ---------------------------------------------------
$missing = @()
foreach ($tool in @("kubectl", "helm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        $missing += $tool
    }
}
if ($missing.Count -gt 0) {
    Write-Host "[ERROR] Missing required tools: $($missing -join ', ')" -ForegroundColor Red
    exit 1
}

# -- 2. Uninstall Helm release ------------------------------------------------
Write-Host "[INFO]  Uninstalling Helm release 'data-profiling'..." -ForegroundColor Yellow
try {
    helm uninstall data-profiling -n data-profiling
    if ($LASTEXITCODE -ne 0) { throw "helm uninstall exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Helm release removed" -ForegroundColor Green
} catch {
    Write-Host "[WARN]  helm uninstall failed (release may already be gone): $_" -ForegroundColor DarkYellow
}

# -- 3. Delete namespace ------------------------------------------------------
Write-Host ""
Write-Host "[INFO]  Deleting namespace 'data-profiling'..." -ForegroundColor Yellow
try {
    kubectl delete namespace data-profiling
    if ($LASTEXITCODE -ne 0) { throw "kubectl delete namespace exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Namespace deleted" -ForegroundColor Green
} catch {
    Write-Host "[WARN]  Namespace deletion failed (may already be gone): $_" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "[OK]    Stopped. Docker Desktop Kubernetes is still running." -ForegroundColor Green
Write-Host ""
