#Requires -Version 5.1
<#
.SYNOPSIS
    Builds, loads, and deploys the data-profiling app to local Kubernetes (Docker Desktop).
#>

Write-Host ""
Write-Host "DataProfiler - Local Startup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Prerequisite checks ---------------------------------------------------
$missing = @()
foreach ($tool in @("docker", "kubectl", "helm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        $missing += $tool
    }
}
if ($missing.Count -gt 0) {
    Write-Host "[ERROR] Missing required tools: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "        Install them and re-run this script." -ForegroundColor Red
    exit 1
}

# -- 2. Switch kubectl context ------------------------------------------------
Write-Host "[INFO]  Switching kubectl context to docker-desktop..." -ForegroundColor Yellow
try {
    kubectl config use-context docker-desktop | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "kubectl config use-context exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Context set to docker-desktop" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to switch kubectl context: $_" -ForegroundColor Red
    exit 1
}

# -- 3. Build Docker image ----------------------------------------------------
Write-Host ""
Write-Host "[INFO]  Building Docker image data-profiling:latest..." -ForegroundColor Yellow
try {
    docker build -t data-profiling:latest .
    if ($LASTEXITCODE -ne 0) { throw "docker build exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Image built successfully" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker build failed: $_" -ForegroundColor Red
    exit 1
}

# -- 4. Export image to tar ---------------------------------------------------
Write-Host ""
Write-Host "[INFO]  Exporting image to data-profiling.tar..." -ForegroundColor Yellow
try {
    docker save data-profiling:latest -o data-profiling.tar
    if ($LASTEXITCODE -ne 0) { throw "docker save exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Image exported" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Image export failed: $_" -ForegroundColor Red
    exit 1
}

# -- 5. Copy image into kind node ---------------------------------------------
Write-Host ""
Write-Host "[INFO]  Copying image into kind node (desktop-control-plane)..." -ForegroundColor Yellow
try {
    docker cp data-profiling.tar desktop-control-plane:/data-profiling.tar
    if ($LASTEXITCODE -ne 0) { throw "docker cp exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Copied to node" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] docker cp failed: $_" -ForegroundColor Red
    Write-Host "        Is the kind node container 'desktop-control-plane' running?" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[INFO]  Importing image inside kind node..." -ForegroundColor Yellow
try {
    docker exec -i desktop-control-plane ctr -n k8s.io images import /data-profiling.tar
    if ($LASTEXITCODE -ne 0) { throw "ctr images import exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Image imported into containerd" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Image import failed: $_" -ForegroundColor Red
    exit 1
}

# -- 6. Deploy with Helm ------------------------------------------------------
Write-Host ""
Write-Host "[INFO]  Deploying with Helm..." -ForegroundColor Yellow
try {
    helm upgrade --install data-profiling charts/data-profiling `
        --namespace data-profiling `
        --create-namespace `
        --set image.pullPolicy=Never
    if ($LASTEXITCODE -ne 0) { throw "helm upgrade exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Helm release deployed" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Helm deploy failed: $_" -ForegroundColor Red
    exit 1
}

# -- 7. Wait for pod ready ----------------------------------------------------
Write-Host ""
Write-Host "[WAIT]  Waiting for pod to be Ready (timeout 120s)..." -ForegroundColor Yellow
try {
    kubectl wait --for=condition=ready pod `
        -l app.kubernetes.io/name=data-profiling `
        -n data-profiling `
        --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "kubectl wait exited with code $LASTEXITCODE" }
    Write-Host "[OK]    Pod is Ready" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Pod did not become ready in time: $_" -ForegroundColor Red
    Write-Host "        Run 'kubectl get pods -n data-profiling' to investigate." -ForegroundColor Red
    exit 1
}

# -- 8. Port-forward (blocking) -----------------------------------------------
Write-Host ""
Write-Host "[OK]    App is running at http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "[INFO]  Starting port-forward -- press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host ""

kubectl port-forward svc/data-profiling 8501:8501 -n data-profiling
