#Requires -Version 5.1
<#
.SYNOPSIS
    Uninstalls a tool's Helm release from local Kubernetes.

.PARAMETER AppName
    Name of the tool to stop. Must match the Helm release name used at deploy time.

.PARAMETER Namespace
    Kubernetes namespace where the tool is deployed. Defaults to 'tools-prod'.

.PARAMETER DeleteNamespace
    If specified, also deletes the namespace. Use with care when multiple tools
    share the same namespace (the default: tools-prod).

.EXAMPLE
    .\stop.ps1 -AppName dataprofile
    .\stop.ps1 -AppName portal -Namespace tools-dev -DeleteNamespace
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [string]$Namespace = "tools-prod",

    [switch]$DeleteNamespace
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) { Write-Host ""
    Write-Host "[INFO]  $msg" -ForegroundColor Yellow }

function Write-Ok([string]$msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "[WARN]  $msg" -ForegroundColor DarkYellow }
function Write-Fail([string]$msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Adoreal Tools — Stop: $AppName" -ForegroundColor Yellow
Write-Host "=======================================" -ForegroundColor Yellow

$missing = @()
foreach ($tool in @("kubectl", "helm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) { Write-Fail "Missing tools: $($missing -join ', ')" }

# ---------------------------------------------------------------------------
# Uninstall Helm release
# ---------------------------------------------------------------------------

Write-Step "Uninstalling Helm release '$AppName' from namespace '$Namespace'"
try {
    helm uninstall $AppName -n $Namespace
    if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
    Write-Ok "Helm release '$AppName' removed"
} catch {
    Write-Warn "helm uninstall failed (release may already be gone): $_"
}

# ---------------------------------------------------------------------------
# Optionally delete namespace
# ---------------------------------------------------------------------------

if ($DeleteNamespace) {
    Write-Step "Deleting namespace '$Namespace'"
    try {
        kubectl delete namespace $Namespace
        if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
        Write-Ok "Namespace '$Namespace' deleted"
    } catch {
        Write-Warn "Namespace deletion failed (may already be gone): $_"
    }
} else {
    Write-Host "[INFO]  Namespace '$Namespace' kept (other tools may still be running)." -ForegroundColor DarkCyan
    Write-Host "        Pass -DeleteNamespace to remove it." -ForegroundColor DarkCyan
}

Write-Host ""
Write-Ok "Done. Docker Desktop Kubernetes is still running."
Write-Host ""