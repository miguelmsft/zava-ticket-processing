# ACR Cloud Build + Container App Update Script
# Bypasses local Docker by building in Azure Container Registry
# Resource names are read dynamically from the active azd environment.

$ErrorActionPreference = "Continue"

# Read resource names from azd environment
$rg = (azd env get-value AZURE_RESOURCE_GROUP 2>$null)
if (-not $rg) { $rg = "rg-$(azd env get-value AZURE_ENV_NAME 2>$null)" }
$prefix = (azd env get-value AZURE_NAMING_PREFIX 2>$null)
if (-not $prefix) { Write-Host "ERROR: AZURE_NAMING_PREFIX not set in azd env" -ForegroundColor Red; exit 1 }
$acr = "${prefix}registry"
$caName = "${prefix}-backend"
$imageName = "backend"
$tag = "deploy-$(Get-Date -Format 'yyyyMMddHHmmss')"
$fullImage = "$acr.azurecr.io/${imageName}:${tag}"

Write-Host "Resource Group: $rg" -ForegroundColor Yellow
Write-Host "ACR: $acr" -ForegroundColor Yellow
Write-Host "Container App: $caName" -ForegroundColor Yellow

Write-Host "=== Step 1: Get current image ===" -ForegroundColor Cyan
$currentImage = az containerapp show --name $caName --resource-group $rg --query "properties.template.containers[0].image" -o tsv 2>$null
Write-Host "Current image: $currentImage"

Write-Host "`n=== Step 2: Build image in ACR (cloud-side) ===" -ForegroundColor Cyan
Write-Host "Image: $fullImage"
Write-Host "Building from ./backend with Dockerfile..."

# Build in ACR - no local Docker needed
az acr build --registry $acr --resource-group $rg --image "${imageName}:${tag}" --file backend/Dockerfile ./backend/ 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: ACR build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 3: Update Container App ===" -ForegroundColor Cyan
az containerapp update --name $caName --resource-group $rg --image $fullImage 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Container App update failed" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 4: Verify new revision ===" -ForegroundColor Cyan
Start-Sleep 10
az containerapp revision list --name $caName --resource-group $rg --query "[].{name:name,created:properties.createdTime,active:properties.active}" -o table

Write-Host "`n=== Step 5: Health check ===" -ForegroundColor Cyan
Start-Sleep 15
$backendUrl = (azd env get-value BACKEND_URL 2>$null)
if (-not $backendUrl) {
    $fqdn = az containerapp show --name $caName --resource-group $rg --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
    $backendUrl = "https://$fqdn"
}
Write-Host "Health endpoint: $backendUrl/health"
$health = Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 30 2>$null
Write-Host "Health: $($health | ConvertTo-Json -Compress)"

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "New image: $fullImage"
