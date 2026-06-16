#Requires -Version 5.1
<#
.SYNOPSIS
    Builds, loads, and deploys any tool to local Kubernetes (Docker Desktop).

.PARAMETER AppName
    Name of the tool to deploy. Must match:
      - A top-level folder in the repo:          <AppName>/
      - A Helm chart folder:                     charts/<AppName>/
    Example: dataprofile, portal, bc-migrator

.PARAMETER Namespace
    Kubernetes namespace to deploy into. Defaults to 'tools-prod'.

.PARAMETER Port
    Local port to forward. Defaults to the containerPort in the chart (8501 for
    Streamlit, 3000 for Next.js, 8000 for FastAPI). Override when needed.

.EXAMPLE
    .\deploy.ps1 -AppName dataprofile
    .\deploy.ps1 -AppName portal -Port 3000
    .\deploy.ps1 -AppName bc-migrator -Port 8000 -Namespace tools-dev
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [string]$Namespace = "tools-prod",

    [int]$Port = 0          # 0 = auto-detect from Helm values
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot | Split-Path -Parent   # scripts/ is one level below repo root

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "[INFO]  $msg" -ForegroundColor Yellow
}

function Write-Ok([string]$msg) {
    Write-Host "[OK]    $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

function Invoke-Cmd([string]$desc, [scriptblock]$cmd) {
    Write-Step $desc
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Fail "$desc failed (exit $LASTEXITCODE)" }
    Write-Ok  "$desc succeeded"
}

# ---------------------------------------------------------------------------
# Resolve port automatically if not supplied
# ---------------------------------------------------------------------------

function Get-DefaultPort([string]$appName, [string]$chartDir) {
    $valuesFile = Join-Path $chartDir "values.yaml"
    if (Test-Path $valuesFile) {
        $match = Select-String -Path $valuesFile -Pattern "^\s*port:\s*(\d+)" | Select-Object -First 1
        if ($match) {
            return [int]($match.Matches[0].Groups[1].Value)
        }
    }
    # Sensible defaults by convention
    if ($appName -match "portal")  { return 3000 }
    if ($appName -match "api|fast|flask") { return 8000 }
    return 8501   # Streamlit default
}

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Adoreal Tools — Deploy: $AppName" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$appDir   = Join-Path $RepoRoot $AppName
$chartDir = Join-Path $RepoRoot "charts" $AppName

if (-not (Test-Path $appDir))   { Write-Fail "App folder not found: $appDir" }
if (-not (Test-Path $chartDir)) { Write-Fail "Helm chart not found: $chartDir" }

if ($Port -eq 0) {
    $Port = Get-DefaultPort -appName $AppName -chartDir $chartDir
    Write-Host "[INFO]  Auto-detected port: $Port" -ForegroundColor DarkCyan
}

$ImageTag = "${AppName}:latest"
$TarFile  = Join-Path $RepoRoot "${AppName}.tar"

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

Write-Step "Checking prerequisites (docker, kubectl, helm)"
$missing = @()
foreach ($tool in @("docker", "kubectl", "helm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) { Write-Fail "Missing tools: $($missing -join ', '). Install them and re-run." }
Write-Ok "All prerequisites found"

# ---------------------------------------------------------------------------
# Switch kubectl context
# ---------------------------------------------------------------------------

Invoke-Cmd "Switching kubectl context to docker-desktop" {
    kubectl config use-context docker-desktop | Out-Null
}

# ---------------------------------------------------------------------------
# Build Docker image
# ---------------------------------------------------------------------------

Invoke-Cmd "Building Docker image $ImageTag (context: $appDir)" {
    docker build -t $ImageTag $appDir
}

# ---------------------------------------------------------------------------
# Export + import into kind node (skip if not using kind)
# ---------------------------------------------------------------------------

$kindNode = "desktop-control-plane"
$kindRunning = docker ps --filter "name=$kindNode" --format "{{.Names}}" 2>$null

if ($kindRunning) {
    Invoke-Cmd "Exporting image to $TarFile" {
        docker save $ImageTag -o $TarFile
    }

    Invoke-Cmd "Copying image into kind node ($kindNode)" {
        docker cp $TarFile "${kindNode}:/tmp/${AppName}.tar"
    }

    Invoke-Cmd "Importing image inside kind node" {
        docker exec -i $kindNode ctr -n k8s.io images import "/tmp/${AppName}.tar"
    }

    Remove-Item $TarFile -ErrorAction SilentlyContinue
    Write-Ok "Temporary tar file cleaned up"
} else {
    Write-Host "[SKIP]  kind node '$kindNode' not running — skipping tar export/import (Docker Desktop native mode)" -ForegroundColor DarkCyan
}

# ---------------------------------------------------------------------------
# Helm deploy
# ---------------------------------------------------------------------------

Invoke-Cmd "Deploying $AppName with Helm to namespace '$Namespace'" {
    helm upgrade --install $AppName (Join-Path $RepoRoot "charts" $AppName) `
        --namespace $Namespace `
        --create-namespace `
        --set image.pullPolicy=Never
}

# ---------------------------------------------------------------------------
# Wait for pod ready
# ---------------------------------------------------------------------------

Invoke-Cmd "Waiting for pod to be Ready (timeout 120s)" {
    kubectl wait --for=condition=ready pod `
        -l "app.kubernetes.io/name=$AppName" `
        -n $Namespace `
        --timeout=120s
}

# ---------------------------------------------------------------------------
# Port-forward (blocking)
# ---------------------------------------------------------------------------

Write-Host ""
Write-Ok "App '$AppName' is running at http://localhost:$Port"
Write-Host ""
Write-Host "[INFO]  Starting port-forward on :$Port — press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host ""

kubectl port-forward "svc/$AppName" "${Port}:${Port}" -n $Namespace