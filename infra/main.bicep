// ===========================================================================
// main.bicep — Zava Processing Inc. Ticket Processing System
// ===========================================================================
// Azure Developer CLI (azd) orchestrator
// Scope: Subscription (creates its own Resource Group)
//
// Resources provisioned:
//   1.  Log Analytics + Application Insights  (monitoring)
//   2.  User-Assigned Managed Identity        (identity)
//   3.  Cosmos DB Serverless + 3 containers   (cosmos)
//   4.  Storage Account + blob containers     (storage)
//   5.  Azure Container Registry (Basic)      (containerRegistry)
//   6.  Azure AI Services + gpt-5-mini + gpt-4.1 + embeddings (aiServices)
//   7.  5x Azure Function Apps (Consumption)  (functions)
//   8.  Container Apps Env + Backend app      (containerApps)
//   9.  Static Web App (Free)                 (staticWebApp)
//  10.  API Management BasicV2 (optional)     (apim)
// ===========================================================================

targetScope = 'subscription'

// ── Parameters ─────────────────────────────────────────────────────────────

@description('Name of the azd environment (used for resource group naming)')
param environmentName string

@description('Primary Azure region for all resources. Default: eastus2')
@allowed([
  'eastus2'          // Best Foundry Agent Service coverage (all models). Requires App Service quota.
  'swedencentral'    // Full Foundry Agent + App Service quota available.
  'westus3'          // App Service quota available; limited Agent Service models (no gpt-5-mini).
])
param location string

@description('Short naming prefix for all resources (3-10 lowercase alphanumeric + hyphens)')
@minLength(3)
@maxLength(10)
param namingPrefix string

@description('Resource group name. Defaults to rg-<environmentName> if not specified.')
param resourceGroupName string = ''

@description('AI model to deploy. Default: gpt-5-mini')
param modelName string = ''

@description('AI model version. Default: 2025-08-07')
param modelVersion string = ''

@description('Deploy API Management gateway (takes 30-45 min). Default: false')
param deployApim bool = false

@description('Principal ID of the deploying user (for Foundry portal access). Set via AZURE_PRINCIPAL_ID.')
param deployerPrincipalId string = ''

// ── Variables ──────────────────────────────────────────────────────────────

// Effective model config — fall back to defaults if env vars are empty
var effectiveModelName = !empty(modelName) ? modelName : 'gpt-5-mini'
var effectiveModelVersion = !empty(modelVersion) ? modelVersion : '2025-08-07'

var tags = {
  'azd-env-name': environmentName
  project: 'zava-ticket-processing'
  'managed-by': 'azd-bicep'
}

// ── Resource Group ─────────────────────────────────────────────────────────

var effectiveResourceGroupName = !empty(resourceGroupName) ? resourceGroupName : 'rg-${environmentName}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: effectiveResourceGroupName
  location: location
  tags: tags
}

// ===========================================================================
// Layer 1: Foundation (no cross-module dependencies)
// ===========================================================================

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
  }
}

module identity 'modules/managed-identity.bicep' = {
  scope: rg
  name: 'managed-identity'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
  }
}

// ===========================================================================
// Layer 2: Data + Registry + AI (depend on Managed Identity for RBAC)
// ===========================================================================

module cosmos 'modules/cosmos.bicep' = {
  scope: rg
  name: 'cosmos'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    principalId: identity.outputs.managedIdentityPrincipalId
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    principalId: identity.outputs.managedIdentityPrincipalId
  }
}

module containerRegistry 'modules/container-registry.bicep' = {
  scope: rg
  name: 'container-registry'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    principalId: identity.outputs.managedIdentityPrincipalId
  }
}

module aiServices 'modules/ai-services.bicep' = {
  scope: rg
  name: 'ai-services'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    modelName: effectiveModelName
    modelVersion: effectiveModelVersion
    principalId: identity.outputs.managedIdentityPrincipalId
    deployerPrincipalId: deployerPrincipalId
  }
}

// Foundry Project — creates a project under the AI Services account
// so that agents are persistent and visible in the Foundry portal.
module foundryProject 'modules/foundry-project.bicep' = {
  scope: rg
  name: 'foundry-project'
  params: {
    location: location
    aiServicesAccountName: aiServices.outputs.aiServicesName
    projectName: 'zava-ticket-processing'
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

// ===========================================================================
// Layer 3: Shared App Service Plan + Function Apps
// ===========================================================================

// Shared B1 Linux App Service Plan for all function apps.
// (Subscription does not have Dynamic VMs quota for Consumption/Y1.)
module funcPlan 'modules/app-service-plan.bicep' = {
  scope: rg
  name: 'func-plan'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
  }
}

// Common function app parameters (reduces repetition)
var funcCommonParams = {
  location: location
  namingPrefix: namingPrefix
  tags: tags
  storageConnectionString: storage.outputs.storageConnectionString
  appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  managedIdentityId: identity.outputs.managedIdentityId
  managedIdentityClientId: identity.outputs.managedIdentityClientId
}

module mcpCosmos 'modules/function-app.bicep' = {
  scope: rg
  name: 'func-mcp-cosmos'
  params: {
    location: funcCommonParams.location
    namingPrefix: funcCommonParams.namingPrefix
    tags: funcCommonParams.tags
    appServicePlanId: funcPlan.outputs.planId
    storageConnectionString: funcCommonParams.storageConnectionString
    appInsightsConnectionString: funcCommonParams.appInsightsConnectionString
    managedIdentityId: funcCommonParams.managedIdentityId
    managedIdentityClientId: funcCommonParams.managedIdentityClientId
    functionName: 'mcp-cosmos'
    serviceName: 'mcp-cosmos'
    extraAppSettings: [
      { name: 'COSMOS_ENDPOINT', value: cosmos.outputs.cosmosEndpoint }
      { name: 'COSMOS_DATABASE_NAME', value: cosmos.outputs.cosmosDatabaseName }
    ]
  }
}

module apiCodeMapping 'modules/function-app.bicep' = {
  scope: rg
  name: 'func-api-code-mapping'
  params: {
    location: funcCommonParams.location
    namingPrefix: funcCommonParams.namingPrefix
    tags: funcCommonParams.tags
    appServicePlanId: funcPlan.outputs.planId
    storageConnectionString: funcCommonParams.storageConnectionString
    appInsightsConnectionString: funcCommonParams.appInsightsConnectionString
    managedIdentityId: funcCommonParams.managedIdentityId
    managedIdentityClientId: funcCommonParams.managedIdentityClientId
    functionName: 'api-codemapping'
    serviceName: 'api-code-mapping'
    extraAppSettings: [
      { name: 'COSMOS_ENDPOINT', value: cosmos.outputs.cosmosEndpoint }
      { name: 'COSMOS_DATABASE_NAME', value: cosmos.outputs.cosmosDatabaseName }
    ]
  }
}

module apiPayment 'modules/function-app.bicep' = {
  scope: rg
  name: 'func-api-payment'
  params: {
    location: funcCommonParams.location
    namingPrefix: funcCommonParams.namingPrefix
    tags: funcCommonParams.tags
    appServicePlanId: funcPlan.outputs.planId
    storageConnectionString: funcCommonParams.storageConnectionString
    appInsightsConnectionString: funcCommonParams.appInsightsConnectionString
    managedIdentityId: funcCommonParams.managedIdentityId
    managedIdentityClientId: funcCommonParams.managedIdentityClientId
    functionName: 'api-payment'
    serviceName: 'api-payment'
    extraAppSettings: [
      { name: 'COSMOS_ENDPOINT', value: cosmos.outputs.cosmosEndpoint }
      { name: 'COSMOS_DATABASE_NAME', value: cosmos.outputs.cosmosDatabaseName }
    ]
  }
}

// ===========================================================================
// Layer 4: Agent Function Apps (depend on Layer 3 function URLs)
// ===========================================================================

module stageB 'modules/function-app.bicep' = {
  scope: rg
  name: 'func-stage-b'
  params: {
    location: funcCommonParams.location
    namingPrefix: funcCommonParams.namingPrefix
    tags: funcCommonParams.tags
    appServicePlanId: funcPlan.outputs.planId
    storageConnectionString: funcCommonParams.storageConnectionString
    appInsightsConnectionString: funcCommonParams.appInsightsConnectionString
    managedIdentityId: funcCommonParams.managedIdentityId
    managedIdentityClientId: funcCommonParams.managedIdentityClientId
    functionName: 'stage-b'
    serviceName: 'stage-b'
    extraAppSettings: [
      { name: 'COSMOS_ENDPOINT', value: cosmos.outputs.cosmosEndpoint }
      { name: 'COSMOS_DATABASE_NAME', value: cosmos.outputs.cosmosDatabaseName }
      { name: 'AI_PROJECT_ENDPOINT', value: foundryProject.outputs.projectEndpoint }
      { name: 'MODEL_DEPLOYMENT_NAME', value: aiServices.outputs.agentModelDeploymentName }
      { name: 'MCP_COSMOS_ENDPOINT', value: '${mcpCosmos.outputs.functionAppUrl}/runtime/webhooks/mcp' }
      { name: 'CODE_MAPPING_API_URL', value: apiCodeMapping.outputs.functionAppUrl }
    ]
  }
}

module stageC 'modules/function-app.bicep' = {
  scope: rg
  name: 'func-stage-c'
  params: {
    location: funcCommonParams.location
    namingPrefix: funcCommonParams.namingPrefix
    tags: funcCommonParams.tags
    appServicePlanId: funcPlan.outputs.planId
    storageConnectionString: funcCommonParams.storageConnectionString
    appInsightsConnectionString: funcCommonParams.appInsightsConnectionString
    managedIdentityId: funcCommonParams.managedIdentityId
    managedIdentityClientId: funcCommonParams.managedIdentityClientId
    functionName: 'stage-c'
    serviceName: 'stage-c'
    extraAppSettings: [
      { name: 'COSMOS_ENDPOINT', value: cosmos.outputs.cosmosEndpoint }
      { name: 'COSMOS_DATABASE_NAME', value: cosmos.outputs.cosmosDatabaseName }
      { name: 'AI_PROJECT_ENDPOINT', value: foundryProject.outputs.projectEndpoint }
      { name: 'MODEL_DEPLOYMENT_NAME', value: aiServices.outputs.agentModelDeploymentName }
      { name: 'MCP_COSMOS_ENDPOINT', value: '${mcpCosmos.outputs.functionAppUrl}/runtime/webhooks/mcp' }
      { name: 'PAYMENT_API_URL', value: apiPayment.outputs.functionAppUrl }
    ]
  }
}

// ===========================================================================
// Layer 5: Frontend Static Web App (deployed before backend so CORS URL is available)
// ===========================================================================

// SWA supported regions: westus2, centralus, eastus2, westeurope, eastasia, plus others.
// swedencentral is NOT a supported SWA region, so we fall back to westeurope.
// westus3 is NOT a supported SWA region, so we fall back to westus2.
var swaLocation = (location == 'swedencentral') ? 'westeurope' : ((location == 'westus3') ? 'westus2' : location)

module staticWebApp 'modules/static-web-app.bicep' = {
  scope: rg
  name: 'static-web-app'
  params: {
    location: location
    swaLocation: swaLocation
    namingPrefix: namingPrefix
    tags: tags
  }
}

// ===========================================================================
// Layer 6: Backend Container App (depends on Stage B/C URLs + Frontend URL for CORS)
// ===========================================================================

module containerApps 'modules/container-apps.bicep' = {
  scope: rg
  name: 'container-apps'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
    acrLoginServer: containerRegistry.outputs.acrLoginServer
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    cosmosEndpoint: cosmos.outputs.cosmosEndpoint
    cosmosDatabaseName: cosmos.outputs.cosmosDatabaseName
    storageBlobEndpoint: storage.outputs.storageBlobEndpoint
    storageAccountName: storage.outputs.storageAccountName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    stageBFunctionUrl: stageB.outputs.functionAppUrl
    stageCFunctionUrl: stageC.outputs.functionAppUrl
    // Content Understanding model names are passed via environment — see container-apps.bicep
    aiServicesEndpoint: aiServices.outputs.aiServicesEndpoint
    cuModelDeploymentName: aiServices.outputs.cuModelDeploymentName
    embeddingsDeploymentName: aiServices.outputs.embeddingsDeploymentName
    frontendUrl: staticWebApp.outputs.staticWebAppUrl
  }
}

// ===========================================================================
// Layer 7: API Management (optional — takes 30-45 min to provision)
// ===========================================================================

module apim 'modules/apim.bicep' = if (deployApim) {
  scope: rg
  name: 'api-management'
  params: {
    location: location
    namingPrefix: namingPrefix
    tags: tags
    mcpCosmosUrl: mcpCosmos.outputs.functionAppUrl
    codeMappingApiUrl: apiCodeMapping.outputs.functionAppUrl
    paymentApiUrl: apiPayment.outputs.functionAppUrl
    appInsightsInstrumentationKey: monitoring.outputs.appInsightsInstrumentationKey
  }
}

// ===========================================================================
// Outputs — consumed by azd for service deployment and by postdeploy.py
// ===========================================================================

// ── Resource Group ─────────────────────────────────────────────────────────
output AZURE_RESOURCE_GROUP string = rg.name

// ── Cosmos DB ──────────────────────────────────────────────────────────────
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.cosmosEndpoint
output AZURE_COSMOS_DATABASE_NAME string = cosmos.outputs.cosmosDatabaseName

// ── Storage ────────────────────────────────────────────────────────────────
output AZURE_STORAGE_BLOB_ENDPOINT string = storage.outputs.storageBlobEndpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.storageAccountName

// ── Container Registry (used by azd for Docker build + push) ───────────────
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.acrLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.acrName

// ── AI Services ────────────────────────────────────────────────────────────
output AZURE_AI_ENDPOINT string = aiServices.outputs.aiServicesEndpoint
output AZURE_AI_PROJECT_ENDPOINT string = foundryProject.outputs.projectEndpoint
output AZURE_AI_PROJECT_NAME string = foundryProject.outputs.projectName
output AZURE_AI_AGENT_MODEL string = aiServices.outputs.agentModelDeploymentName
output AZURE_AI_CU_MODEL string = aiServices.outputs.cuModelDeploymentName
output AZURE_AI_EMBEDDINGS_MODEL string = aiServices.outputs.embeddingsDeploymentName

// ── Backend Container App ──────────────────────────────────────────────────
output SERVICE_BACKEND_NAME string = containerApps.outputs.backendName
output SERVICE_BACKEND_URI string = containerApps.outputs.backendUrl

// ── Frontend Static Web App ────────────────────────────────────────────────
output SERVICE_FRONTEND_URI string = staticWebApp.outputs.staticWebAppUrl

// ── Function App URLs (for postdeploy and debugging) ───────────────────────
output SERVICE_MCP_COSMOS_URI string = mcpCosmos.outputs.functionAppUrl
output SERVICE_API_CODE_MAPPING_URI string = apiCodeMapping.outputs.functionAppUrl
output SERVICE_API_PAYMENT_URI string = apiPayment.outputs.functionAppUrl
output SERVICE_STAGE_B_URI string = stageB.outputs.functionAppUrl
output SERVICE_STAGE_C_URI string = stageC.outputs.functionAppUrl

// ── API Management (conditional) ───────────────────────────────────────────
// Note: When deployApim=true, retrieve the gateway URL from the APIM resource
// after deployment (e.g., via postdeploy.py or `az apim show`)
output AZURE_DEPLOY_APIM bool = deployApim
