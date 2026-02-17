#!/usr/bin/env bash
# ===========================================================================
# deploy.sh — Interactive deployment script for Zava Ticket Processing
# ===========================================================================
# This script guides you through deploying the full system to Azure using
# Azure Developer CLI (azd) + Bicep.
#
# Usage:
#   ./scripts/deploy.sh              # Interactive mode
#   ./scripts/deploy.sh --skip-login # Skip azd/az login
#
# Prerequisites:
#   - Azure Developer CLI (azd)  → https://aka.ms/azd-install
#   - Azure CLI (az)             → https://aka.ms/install-az
#   - Python 3.12+               → https://python.org
#   - Docker                     → https://docker.com
# ===========================================================================

set -euo pipefail

SKIP_LOGIN=false
for arg in "$@"; do
    case "$arg" in
        --skip-login) SKIP_LOGIN=true ;;
    esac
done

# ── Colors ──────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m'

header()  { echo -e "\n${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"; echo -e "${CYAN}║  $1${NC}"; echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"; }
step()    { echo -e "\n${YELLOW}► Step $1/9: $2${NC}"; }
ok()      { echo -e "  ${GREEN}✓ $1${NC}"; }
warn()    { echo -e "  ${YELLOW}⚠ $1${NC}"; }
fail()    { echo -e "  ${RED}✗ $1${NC}"; }

header "Zava Processing Inc. — Azure Deployment"

# ===========================================================================
# Step 1: Pre-flight checks
# ===========================================================================
step 1 "Pre-flight checks"

MISSING=()

if command -v azd &>/dev/null; then
    ok "azd found: $(azd version 2>&1 | head -1)"
else
    MISSING+=("azd")
    fail "azd not found. Install: https://aka.ms/azd-install"
fi

if command -v az &>/dev/null; then
    ok "az CLI found: $(az version --output tsv 2>&1 | head -1)"
else
    MISSING+=("az")
    fail "az CLI not found. Install: https://aka.ms/install-az"
fi

if command -v python3 &>/dev/null; then
    ok "Python found: $(python3 --version 2>&1)"
elif command -v python &>/dev/null; then
    ok "Python found: $(python --version 2>&1)"
else
    MISSING+=("python")
    fail "Python not found. Install: https://python.org"
fi

if command -v docker &>/dev/null; then
    if docker info &>/dev/null; then
        ok "Docker is running"
    else
        warn "Docker is installed but not running. Start Docker before deploying."
    fi
else
    warn "Docker not found. Required for backend container. Install: https://docker.com"
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    fail "Missing required tools: ${MISSING[*]}. Install them and re-run."
    exit 1
fi

# ===========================================================================
# Step 2: Authentication
# ===========================================================================
step 2 "Authentication"

if [ "$SKIP_LOGIN" = false ]; then
    echo -e "  ${GRAY}Which Azure account do you want to use?${NC}"
    echo -e "  ${GRAY}Leave blank to use the default browser login flow.${NC}"
    echo -e "  ${GRAY}Or enter an email (e.g., user@contoso.com) to log in with a specific account.${NC}"
    echo ""
    read -rp "  Azure login email (press Enter for default): " LOGIN_EMAIL
    echo ""
    read -rp "  Azure AD Tenant ID (press Enter to skip): " TENANT_ID

    # Build az login args
    AZ_LOGIN_ARGS=()
    if [ -n "$LOGIN_EMAIL" ]; then
        AZ_LOGIN_ARGS+=("--login-hint" "$LOGIN_EMAIL")
    fi
    if [ -n "$TENANT_ID" ]; then
        AZ_LOGIN_ARGS+=("--tenant" "$TENANT_ID")
    fi

    # Log in with az CLI first (supports --login-hint)
    echo -e "  ${GRAY}Logging in to Azure CLI...${NC}"
    az login "${AZ_LOGIN_ARGS[@]}"
    ok "az CLI authenticated"

    # Log in to azd (uses the same browser session / cached token)
    echo -e "  ${GRAY}Logging in to Azure Developer CLI...${NC}"
    if [ -n "$TENANT_ID" ]; then
        azd auth login --tenant-id "$TENANT_ID"
    else
        azd auth login
    fi
    ok "azd authenticated"

    if [ -n "$LOGIN_EMAIL" ]; then
        ok "Logged in as: $LOGIN_EMAIL"
    fi
else
    ok "Skipping login (--skip-login)"
fi

# ===========================================================================
# Step 3: Subscription selection
# ===========================================================================
step 3 "Subscription selection"

echo -e "  ${GRAY}Fetching subscriptions...${NC}"
SUB_JSON=$(az account list --output json 2>/dev/null)
SUB_COUNT=$(echo "$SUB_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")

if [ "$SUB_COUNT" -eq 0 ]; then
    fail "No Azure subscriptions found. Run 'az login' first."
    exit 1
fi

echo ""
echo "$SUB_JSON" | python3 -c "
import sys, json
subs = json.load(sys.stdin)
for i, s in enumerate(subs):
    marker = ' (current)' if s.get('isDefault') else ''
    print(f'  [{i+1}] {s[\"name\"]} ({s[\"id\"]}){marker}')
"
echo ""

read -rp "  Select subscription [1-$SUB_COUNT] (press Enter for current): " SUB_CHOICE

if [ -z "$SUB_CHOICE" ]; then
    SELECTED_SUB_ID=$(echo "$SUB_JSON" | python3 -c "import sys,json; subs=json.load(sys.stdin); print(next(s['id'] for s in subs if s.get('isDefault')))")
    SELECTED_SUB_NAME=$(echo "$SUB_JSON" | python3 -c "import sys,json; subs=json.load(sys.stdin); print(next(s['name'] for s in subs if s.get('isDefault')))")
else
    IDX=$((SUB_CHOICE - 1))
    SELECTED_SUB_ID=$(echo "$SUB_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$IDX]['id'])")
    SELECTED_SUB_NAME=$(echo "$SUB_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$IDX]['name'])")
fi

az account set --subscription "$SELECTED_SUB_ID"
ok "Using subscription: $SELECTED_SUB_NAME"

# ===========================================================================
# Step 4: Naming prefix
# ===========================================================================
step 4 "Naming prefix"

echo -e "  ${GRAY}This prefix is used for all Azure resource names.${NC}"
echo -e "  ${GRAY}Requirements: 3-10 chars, lowercase alphanumeric + hyphens.${NC}"
echo -e "  ${GRAY}Example: 'zava' → zava-cosmos, zava-func-stage-b, etc.${NC}"
echo ""

while true; do
    read -rp "  Enter naming prefix (default: zava): " NAMING_PREFIX
    NAMING_PREFIX=${NAMING_PREFIX:-zava}
    NAMING_PREFIX=$(echo "$NAMING_PREFIX" | tr '[:upper:]' '[:lower:]')
    if [[ "$NAMING_PREFIX" =~ ^[a-z][a-z0-9-]{2,9}$ ]]; then
        break
    else
        fail "Invalid prefix. Use 3-10 lowercase alphanumeric + hyphens, starting with a letter."
    fi
done

ok "Naming prefix: $NAMING_PREFIX"

# ===========================================================================
# Step 5: Region selection
# ===========================================================================
step 5 "Region selection"

echo -e "  ${GRAY}Recommended region: eastus2 (best coverage for gpt-5-mini + Content Understanding + Agent Service)${NC}"
echo ""
echo -e "  ${GRAY}Supported regions with full feature coverage:${NC}"
echo -e "  ${GRAY}  eastus2       — East US 2 (recommended)${NC}"
echo -e "  ${GRAY}  eastus        — East US${NC}"
echo -e "  ${GRAY}  swedencentral — Sweden Central${NC}"
echo -e "  ${GRAY}  westus        — West US${NC}"
echo ""

read -rp "  Enter Azure region (default: eastus2): " LOCATION
LOCATION=${LOCATION:-eastus2}

ok "Region: $LOCATION"

# ===========================================================================
# Step 6: Model selection
# ===========================================================================
step 6 "AI Model selection"

echo -e "  ${GRAY}Available models (Global Standard deployment):${NC}"
echo -e "  ${GRAY}  [1] gpt-5-mini (2025-08-07) — Recommended, 400K context, no registration${NC}"
echo -e "  ${GRAY}  [2] gpt-4o (2024-11-20) — Proven, 128K context${NC}"
echo -e "  ${GRAY}  [3] gpt-4.1 (2025-04-14) — Balanced, 1M context${NC}"
echo ""

read -rp "  Select model [1-3] (default: 1): " MODEL_CHOICE
case "$MODEL_CHOICE" in
    2) MODEL_NAME="gpt-4o"; MODEL_VERSION="2024-11-20" ;;
    3) MODEL_NAME="gpt-4.1"; MODEL_VERSION="2025-04-14" ;;
    *) MODEL_NAME="gpt-5-mini"; MODEL_VERSION="2025-08-07" ;;
esac

ok "Model: $MODEL_NAME (version $MODEL_VERSION)"

# ===========================================================================
# Step 7: APIM selection
# ===========================================================================
step 7 "API Management (optional)"

echo -e "  ${GRAY}APIM BasicV2 provides a centralized AI Gateway for MCP tool calls.${NC}"
echo -e "  ${GRAY}⚠ Provisioning takes 30-45 minutes. Skip for faster initial deployment.${NC}"
echo ""

read -rp "  Deploy APIM? (y/N): " APIM_CHOICE
DEPLOY_APIM=false
if [[ "$APIM_CHOICE" =~ ^[Yy]$ ]]; then
    DEPLOY_APIM=true
fi

if [ "$DEPLOY_APIM" = true ]; then ok "APIM: Will be deployed"; else ok "APIM: Skipped (agents call functions directly)"; fi

# ===========================================================================
# Step 8: Confirmation
# ===========================================================================
step 8 "Confirm deployment"

ENV_NAME="${NAMING_PREFIX}-prod"
APIM_LABEL=$( [ "$DEPLOY_APIM" = true ] && echo "Yes (adds ~35 min)" || echo "No" )
TIME_EST=$( [ "$DEPLOY_APIM" = true ] && echo "40-55 min" || echo "10-15 min" )

echo ""
echo -e "  ${WHITE}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "  ${WHITE}│  Deployment Summary                                         │${NC}"
echo -e "  ${WHITE}├─────────────────────────────────────────────────────────────┤${NC}"
echo -e "  ${WHITE}│  Subscription:   $SELECTED_SUB_NAME${NC}"
echo -e "  ${WHITE}│  Resource Group:  rg-${ENV_NAME}${NC}"
echo -e "  ${WHITE}│  Naming Prefix:  $NAMING_PREFIX${NC}"
echo -e "  ${WHITE}│  Region:         $LOCATION${NC}"
echo -e "  ${WHITE}│  Model:          $MODEL_NAME ($MODEL_VERSION)${NC}"
echo -e "  ${WHITE}│  APIM:           $APIM_LABEL${NC}"
echo -e "  ${WHITE}│  Estimated time: $TIME_EST${NC}"
echo -e "  ${WHITE}│  Estimated cost: ~\$2-5/day (demo scale)${NC}"
echo -e "  ${WHITE}└─────────────────────────────────────────────────────────────┘${NC}"
echo ""

read -rp "  Proceed with deployment? (Y/n): " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo -e "\n  ${GRAY}Deployment cancelled.${NC}"
    exit 0
fi

# ===========================================================================
# Step 9: Deploy with azd
# ===========================================================================
step 9 "Deploying with Azure Developer CLI"

# Initialize azd environment
echo -e "  ${GRAY}Initializing azd environment: $ENV_NAME${NC}"
azd env new "$ENV_NAME" 2>/dev/null || true

# Set all environment variables
echo -e "  ${GRAY}Setting environment variables...${NC}"
azd env set AZURE_LOCATION "$LOCATION"
azd env set AZURE_NAMING_PREFIX "$NAMING_PREFIX"
azd env set AZURE_MODEL_NAME "$MODEL_NAME"
azd env set AZURE_MODEL_VERSION "$MODEL_VERSION"
azd env set AZURE_SUBSCRIPTION_ID "$SELECTED_SUB_ID"

ok "Environment configured"

# Run provision + deploy
echo ""
echo -e "  ${CYAN}─── Starting 'azd up' (provision + deploy) ───${NC}"
echo ""

if [ "$DEPLOY_APIM" = true ]; then
    azd up --no-prompt -- --parameters deployApim=true
else
    azd up --no-prompt
fi

# ===========================================================================
# Done!
# ===========================================================================
header "Deployment Complete!"

echo ""
echo -e "  ${GREEN}Your Zava Ticket Processing system is now live!${NC}"
echo ""
echo -e "  ${CYAN}Deployed endpoints:${NC}"
echo -e "    Frontend:  $(azd env get-value SERVICE_FRONTEND_URI 2>/dev/null || echo 'N/A')"
echo -e "    Backend:   $(azd env get-value SERVICE_BACKEND_URI 2>/dev/null || echo 'N/A')"
echo ""
echo -e "  ${CYAN}Useful commands:${NC}"
echo -e "  ${GRAY}  azd monitor         — Open Azure Monitor dashboard${NC}"
echo -e "  ${GRAY}  azd deploy          — Re-deploy code changes${NC}"
echo -e "  ${GRAY}  azd down            — Tear down all resources${NC}"
echo -e "  ${GRAY}  azd env get-values  — Show all output values${NC}"
echo ""
