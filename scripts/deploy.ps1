# ===========================================================================
# deploy.ps1 — Interactive deployment script for Zava Ticket Processing
# ===========================================================================
# This script guides you through deploying the full system to Azure using
# Azure Developer CLI (azd) + Bicep.
#
# Usage:
#   .\scripts\deploy.ps1              # Interactive mode (prompts for all values)
#   .\scripts\deploy.ps1 -SkipLogin   # Skip azd/az login (already authenticated)
#
# Prerequisites:
#   - Azure Developer CLI (azd)  → https://aka.ms/azd-install
#   - Azure CLI (az)             → https://aka.ms/install-az
#   - Python 3.12+               → https://python.org
#   - Docker Desktop             → https://docker.com (for backend container)
# ===========================================================================

param(
    [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"

# ── Colors ──────────────────────────────────────────────────────────────────
function Write-Header($text) { Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan; Write-Host "║  $text" -ForegroundColor Cyan; Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan }
function Write-Step($num, $text) { Write-Host "`n► Step $num/9: $text" -ForegroundColor Yellow }
function Write-Ok($text) { Write-Host "  ✓ $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  ⚠ $text" -ForegroundColor DarkYellow }
function Write-Fail($text) { Write-Host "  ✗ $text" -ForegroundColor Red }

Write-Header "Zava Processing Inc. — Azure Deployment"

# ===========================================================================
# Step 1: Pre-flight checks
# ===========================================================================
Write-Step 1 "Pre-flight checks"

$missing = @()

# Check azd
if (Get-Command azd -ErrorAction SilentlyContinue) {
    $azdVersion = (azd version 2>&1) -join ""
    Write-Ok "azd found: $azdVersion"
} else {
    $missing += "azd"
    Write-Fail "azd not found. Install: https://aka.ms/azd-install"
}

# Check az CLI
if (Get-Command az -ErrorAction SilentlyContinue) {
    $azVersion = (az version --output tsv 2>&1 | Select-Object -First 1)
    Write-Ok "az CLI found: $azVersion"
} else {
    $missing += "az"
    Write-Fail "az CLI not found. Install: https://aka.ms/install-az"
}

# Check Python
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyVersion = (python --version 2>&1) -join ""
    Write-Ok "Python found: $pyVersion"
} else {
    $missing += "python"
    Write-Fail "Python not found. Install: https://python.org"
}

# Check Docker
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $dockerRunning = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Docker is running"
    } else {
        Write-Warn "Docker is installed but not running. Start Docker Desktop before deploying."
    }
} else {
    Write-Warn "Docker not found. Required for backend container build. Install: https://docker.com"
}

if ($missing.Count -gt 0) {
    Write-Fail "Missing required tools: $($missing -join ', '). Install them and re-run."
    exit 1
}

# ===========================================================================
# Step 2: Authentication
# ===========================================================================
Write-Step 2 "Authentication"

if (-not $SkipLogin) {
    Write-Host "  Which Azure account do you want to use?" -ForegroundColor Gray
    Write-Host "  Leave blank to use the default browser login flow." -ForegroundColor Gray
    Write-Host "  Or enter an email (e.g., user@contoso.com) to log in with a specific account." -ForegroundColor Gray
    Write-Host ""
    $loginEmail = Read-Host "  Azure login email (press Enter for default)"
    Write-Host ""

    # Optionally specify a tenant ID for orgs with multiple tenants
    $tenantId = Read-Host "  Azure AD Tenant ID (press Enter to skip)"

    # Build az login args
    $azLoginArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($loginEmail)) {
        $azLoginArgs += "--login-hint"
        $azLoginArgs += $loginEmail
    }
    if (-not [string]::IsNullOrWhiteSpace($tenantId)) {
        $azLoginArgs += "--tenant"
        $azLoginArgs += $tenantId
    }

    # Log in with az CLI first (supports --login-hint)
    Write-Host "  Logging in to Azure CLI..." -ForegroundColor Gray
    az login @azLoginArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "az login failed"
        exit 1
    }
    Write-Ok "az CLI authenticated"

    # Log in to azd (uses the same browser session / cached token)
    Write-Host "  Logging in to Azure Developer CLI..." -ForegroundColor Gray
    if (-not [string]::IsNullOrWhiteSpace($tenantId)) {
        azd auth login --tenant-id $tenantId
    } else {
        azd auth login
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "azd auth login failed"
        exit 1
    }
    Write-Ok "azd authenticated"

    if (-not [string]::IsNullOrWhiteSpace($loginEmail)) {
        Write-Ok "Logged in as: $loginEmail"
    }
} else {
    Write-Ok "Skipping login (--SkipLogin)"
}

# ===========================================================================
# Step 3: Subscription selection
# ===========================================================================
Write-Step 3 "Subscription selection"

Write-Host "  Fetching subscriptions..." -ForegroundColor Gray
$subs = az account list --output json 2>$null | ConvertFrom-Json
if (-not $subs -or $subs.Count -eq 0) {
    Write-Fail "No Azure subscriptions found. Run 'az login' first."
    exit 1
}

Write-Host ""
for ($i = 0; $i -lt $subs.Count; $i++) {
    $marker = if ($subs[$i].isDefault) { " (current)" } else { "" }
    Write-Host "  [$($i + 1)] $($subs[$i].name) ($($subs[$i].id))$marker"
}
Write-Host ""
$subChoice = Read-Host "  Select subscription [1-$($subs.Count)] (press Enter for current)"
if ([string]::IsNullOrWhiteSpace($subChoice)) {
    $selectedSub = $subs | Where-Object { $_.isDefault } | Select-Object -First 1
} else {
    $idx = [int]$subChoice - 1
    $selectedSub = $subs[$idx]
}

az account set --subscription $selectedSub.id
Write-Ok "Using subscription: $($selectedSub.name)"

# ===========================================================================
# Step 4: Naming prefix
# ===========================================================================
Write-Step 4 "Naming prefix"

Write-Host "  This prefix is used for all Azure resource names." -ForegroundColor Gray
Write-Host "  Requirements: 3-10 chars, lowercase alphanumeric + hyphens." -ForegroundColor Gray
Write-Host "  Example: 'zava' → zava-cosmos, zava-func-stage-b, etc." -ForegroundColor Gray
Write-Host ""

do {
    $namingPrefix = Read-Host "  Enter naming prefix (default: zava)"
    if ([string]::IsNullOrWhiteSpace($namingPrefix)) { $namingPrefix = "zava" }
    $namingPrefix = $namingPrefix.ToLower()
    $valid = $namingPrefix -match '^[a-z][a-z0-9-]{2,9}$'
    if (-not $valid) { Write-Fail "Invalid prefix. Use 3-10 lowercase alphanumeric + hyphens, starting with a letter." }
} while (-not $valid)

Write-Ok "Naming prefix: $namingPrefix"

# ===========================================================================
# Step 5: Region selection
# ===========================================================================
Write-Step 5 "Region selection"

Write-Host "  Recommended region: eastus2 (best coverage for gpt-5-mini + Content Understanding + Agent Service)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Supported regions with full feature coverage:" -ForegroundColor Gray
Write-Host "    eastus2       — East US 2 (recommended)" -ForegroundColor Gray
Write-Host "    eastus        — East US" -ForegroundColor Gray
Write-Host "    swedencentral — Sweden Central" -ForegroundColor Gray
Write-Host "    westus        — West US" -ForegroundColor Gray
Write-Host ""

$location = Read-Host "  Enter Azure region (default: eastus2)"
if ([string]::IsNullOrWhiteSpace($location)) { $location = "eastus2" }

Write-Ok "Region: $location"

# ===========================================================================
# Step 6: Model selection
# ===========================================================================
Write-Step 6 "AI Model selection"

Write-Host "  Available models (Global Standard deployment):" -ForegroundColor Gray
Write-Host "    [1] gpt-5-mini (2025-08-07) — Recommended, 400K context, no registration" -ForegroundColor Gray
Write-Host "    [2] gpt-4o (2024-11-20) — Proven, 128K context" -ForegroundColor Gray
Write-Host "    [3] gpt-4.1 (2025-04-14) — Balanced, 1M context" -ForegroundColor Gray
Write-Host ""

$modelChoice = Read-Host "  Select model [1-3] (default: 1)"
switch ($modelChoice) {
    "2" { $modelName = "gpt-4o"; $modelVersion = "2024-11-20" }
    "3" { $modelName = "gpt-4.1"; $modelVersion = "2025-04-14" }
    default { $modelName = "gpt-5-mini"; $modelVersion = "2025-08-07" }
}

Write-Ok "Model: $modelName (version $modelVersion)"

# ===========================================================================
# Step 7: APIM selection
# ===========================================================================
Write-Step 7 "API Management (optional)"

Write-Host "  APIM BasicV2 provides a centralized AI Gateway for MCP tool calls." -ForegroundColor Gray
Write-Host "  ⚠ Provisioning takes 30-45 minutes. Skip for faster initial deployment." -ForegroundColor Gray
Write-Host ""

$apimChoice = Read-Host "  Deploy APIM? (y/N)"
$deployApim = ($apimChoice -eq "y" -or $apimChoice -eq "Y")

if ($deployApim) { Write-Ok "APIM: Will be deployed" } else { Write-Ok "APIM: Skipped (agents call functions directly)" }

# ===========================================================================
# Step 8: Confirmation
# ===========================================================================
Write-Step 8 "Confirm deployment"

$envName = "$namingPrefix-prod"

Write-Host ""
Write-Host "  ┌─────────────────────────────────────────────────────────────┐" -ForegroundColor White
Write-Host "  │  Deployment Summary                                         │" -ForegroundColor White
Write-Host "  ├─────────────────────────────────────────────────────────────┤" -ForegroundColor White
Write-Host "  │  Subscription:  $($selectedSub.name)" -ForegroundColor White
Write-Host "  │  Resource Group: rg-$envName" -ForegroundColor White
Write-Host "  │  Naming Prefix: $namingPrefix" -ForegroundColor White
Write-Host "  │  Region:        $location" -ForegroundColor White
Write-Host "  │  Model:         $modelName ($modelVersion)" -ForegroundColor White
Write-Host "  │  APIM:          $(if ($deployApim) {'Yes (adds ~35 min)'} else {'No'})" -ForegroundColor White
Write-Host "  │                                                             │" -ForegroundColor White
Write-Host "  │  Resources to create:                                       │" -ForegroundColor White
Write-Host "  │    • Log Analytics + App Insights                           │" -ForegroundColor White
Write-Host "  │    • User-Assigned Managed Identity                         │" -ForegroundColor White
Write-Host "  │    • Cosmos DB (Serverless) + 3 containers                  │" -ForegroundColor White
Write-Host "  │    • Storage Account + blob container                       │" -ForegroundColor White
Write-Host "  │    • Container Registry (Basic)                             │" -ForegroundColor White
Write-Host "  │    • Azure AI Services + $modelName deployment       │" -ForegroundColor White
Write-Host "  │    • 5x Azure Function Apps (Python Consumption)            │" -ForegroundColor White
Write-Host "  │    • Container Apps Env + Backend (FastAPI)                  │" -ForegroundColor White
Write-Host "  │    • Static Web App (React frontend)                        │" -ForegroundColor White
if ($deployApim) {
Write-Host "  │    • API Management (BasicV2)                               │" -ForegroundColor White
}
Write-Host "  │                                                             │" -ForegroundColor White
Write-Host "  │  Estimated time: $(if ($deployApim) {'40-55 min'} else {'10-15 min'})                                │" -ForegroundColor White
Write-Host "  │  Estimated cost: ~$2-5/day (demo scale)                     │" -ForegroundColor White
Write-Host "  └─────────────────────────────────────────────────────────────┘" -ForegroundColor White
Write-Host ""

$confirm = Read-Host "  Proceed with deployment? (Y/n)"
if ($confirm -eq "n" -or $confirm -eq "N") {
    Write-Host "`n  Deployment cancelled." -ForegroundColor Gray
    exit 0
}

# ===========================================================================
# Step 9: Deploy with azd
# ===========================================================================
Write-Step 9 "Deploying with Azure Developer CLI"

# Initialize azd environment
Write-Host "  Initializing azd environment: $envName" -ForegroundColor Gray
azd env new $envName 2>$null

# Set all environment variables
Write-Host "  Setting environment variables..." -ForegroundColor Gray
azd env set AZURE_LOCATION $location
azd env set AZURE_NAMING_PREFIX $namingPrefix
azd env set AZURE_MODEL_NAME $modelName
azd env set AZURE_MODEL_VERSION $modelVersion
azd env set AZURE_SUBSCRIPTION_ID $selectedSub.id

Write-Ok "Environment configured"

# Run provision + deploy
Write-Host ""
Write-Host "  ─── Starting 'azd up' (provision + deploy) ───" -ForegroundColor Cyan
Write-Host ""

if ($deployApim) {
    # Pass deployApim as an override parameter
    azd up --no-prompt -- --parameters deployApim=true
} else {
    azd up --no-prompt
}

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Deployment failed. Check the output above for errors."
    Write-Host "  Tip: Run 'azd provision' and 'azd deploy' separately to isolate the issue." -ForegroundColor Gray
    exit 1
}

# ===========================================================================
# Done!
# ===========================================================================
Write-Header "Deployment Complete!"

Write-Host ""
Write-Host "  Your Zava Ticket Processing system is now live!" -ForegroundColor Green
Write-Host ""

# Show deployed URLs
$outputs = azd env get-values 2>$null
Write-Host "  Deployed endpoints:" -ForegroundColor Cyan
Write-Host "    Frontend:  $(azd env get-value SERVICE_FRONTEND_URI 2>$null)" -ForegroundColor White
Write-Host "    Backend:   $(azd env get-value SERVICE_BACKEND_URI 2>$null)" -ForegroundColor White
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor Cyan
Write-Host "    azd monitor         — Open Azure Monitor dashboard" -ForegroundColor Gray
Write-Host "    azd deploy          — Re-deploy code changes" -ForegroundColor Gray
Write-Host "    azd down            — Tear down all resources" -ForegroundColor Gray
Write-Host "    azd env get-values  — Show all output values" -ForegroundColor Gray
Write-Host ""
