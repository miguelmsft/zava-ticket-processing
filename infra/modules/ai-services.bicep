// ---------------------------------------------------------------------------
// Module: ai-services.bicep
// Creates: Azure AI Services (Foundry resource) + 3 model deployments:
//   1. gpt-5-mini  — Foundry Agent V2 (Stage B + Stage C)
//   2. gpt-4.1     — Content Understanding (PDF extraction, Stage A)
//   3. text-embedding-3-large — Content Understanding analyzer training
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

// ── Agent model (gpt-5-mini for Stage B + Stage C) ─────────────────────────
@description('Agent model to deploy (e.g., gpt-5-mini, gpt-4o)')
param modelName string = 'gpt-5-mini'

@description('Agent model version (e.g., 2025-08-07)')
param modelVersion string = '2025-08-07'

// ── Content Understanding model (gpt-4.1 — recommended by Microsoft) ───────
@description('Content Understanding completion model')
param cuModelName string = 'gpt-4.1'

@description('Content Understanding completion model version')
param cuModelVersion string = '2025-04-14'

// ── Embeddings model (for Content Understanding analyzer training) ──────────
@description('Embeddings model for Content Understanding')
param embeddingsModelName string = 'text-embedding-3-large'

@description('Principal ID for RBAC role assignment (Managed Identity)')
param principalId string = ''

@description('Principal ID of the deploying user (for Foundry portal access)')
param deployerPrincipalId string = ''

// ── Azure AI Services Account (Foundry Resource) ───────────────────────────
// This single resource supports:
// - Azure OpenAI model deployments (gpt-5-mini for agents)
// - Content Understanding (prebuilt-invoice analyzer)
// - Agent Service V2 (New)
resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: '${namingPrefix}-ai'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: '${namingPrefix}-ai'
    publicNetworkAccess: 'Enabled'
    // Disable local auth in production; use Managed Identity
    disableLocalAuth: false
    // Enable Foundry project management — allows creating projects as sub-resources
    // Required for: Microsoft.CognitiveServices/accounts/projects
    allowProjectManagement: true
  }
}

// ── Model Deployment: gpt-5-mini (Global Standard) ─────────────────────────
// GPT-5 mini: No registration required, supports Responses API, 
// Functions/Tools/Parallel tool calling, Structured outputs
// Region: Available in East US 2 via Global Standard
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: 80 // 80K tokens per minute — prevents 429s on back-to-back Stage B→C
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// ── Model Deployment: gpt-4.1 (Global Standard) ────────────────────────────
// GPT-4.1: Recommended model for Content Understanding (field extraction,
// document analysis, invoice parsing). Supports Chat Completions API.
// See: https://learn.microsoft.com/azure/ai-services/content-understanding/concepts/models-deployments
resource cuModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: cuModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 80 // 80K tokens per minute — headroom for Content Understanding
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: cuModelName
      version: cuModelVersion
    }
  }
  dependsOn: [modelDeployment] // Serial deployment to avoid conflicts
}

// ── Model Deployment: text-embedding-3-large ────────────────────────────────
// Required by Content Understanding for labeled samples and in-context learning
// to improve analyzer quality.
resource embeddingsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: embeddingsModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingsModelName
      version: '1' // text-embedding-3-large uses version "1"
    }
  }
  dependsOn: [cuModelDeployment] // Serial deployment to avoid conflicts
}

// ── RBAC: Cognitive Services OpenAI User ────────────────────────────────────
// Allows the Managed Identity to call the OpenAI APIs (chat, responses, agents)
resource aiOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aiServices.id, principalId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Cognitive Services Contributor ────────────────────────────────────
// Allows the Managed Identity to create/manage agent versions
resource aiContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aiServices.id, principalId, '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68')
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Azure AI User (Deploying User) ────────────────────────────────────
// Allows the human deployer to view agents in the Foundry V2 portal (ai.azure.com)
// Role: Azure AI User (53ca6127-db72-4b80-b1b0-d745d6d5456d)
// This grants reader access to AI projects + data actions for agent management.
resource aiUserForDeployer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(aiServices.id, deployerPrincipalId, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesId string = aiServices.id
output agentModelDeploymentName string = modelDeployment.name
output cuModelDeploymentName string = cuModelDeployment.name
output embeddingsDeploymentName string = embeddingsDeployment.name
