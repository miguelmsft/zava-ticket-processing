// ---------------------------------------------------------------------------
// Module: foundry-project.bicep
// Creates: A Foundry project under an existing Azure AI Services account
//
// This enables:
//   - Persistent Foundry Agent V2 agents visible in the Foundry portal
//   - Project-scoped agent management (create, get, update, list)
//   - Agent isolation per project workspace
//
// Resource type: Microsoft.CognitiveServices/accounts/projects
// API version:   2025-04-01-preview (required for Foundry project support)
//
// Reference: https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects
// ---------------------------------------------------------------------------

@description('Azure region for the project (must match AI Services account region)')
param location string

@description('Name of the parent Azure AI Services account')
param aiServicesAccountName string

@description('Name for the Foundry project')
param projectName string = 'zava-ticket-processing'

@description('Tags to apply to the project')
param tags object = {}

@description('Principal ID of the user-assigned managed identity to grant Azure AI User role')
param managedIdentityPrincipalId string = ''

@description('Resource ID of the Application Insights instance to connect for Foundry tracing')
param appInsightsId string = ''

@description('Connection string of the Application Insights instance')
param appInsightsConnectionString string = ''

// ── Reference the existing AI Services account ─────────────────────────────
resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

// ── Foundry Project ────────────────────────────────────────────────────────
// Creates a project under the AI Services account. Projects are isolated
// workspaces where agents, evaluations, and files are organized.
// Agents created within this project will be visible in the Foundry portal
// at https://ai.azure.com under this project's scope.
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiServicesAccount
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// ── Outputs ────────────────────────────────────────────────────────────────

// ── RBAC: Azure AI User on AI Services account ────────────────────────────
// The Azure AI User built-in role (53ca6127-db72-4b80-b1b0-d745d6d5456d) includes
// Microsoft.CognitiveServices/* data actions, which covers:
//   - AIServices/agents/write  (create/update agents)
//   - AIServices/agents/read   (list/get agents)
//   - OpenAI/*                 (responses API)
// Reference: https://aka.ms/FoundryPermissions
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource aiUserRoleOnAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(managedIdentityPrincipalId)) {
  name: guid(aiServicesAccount.id, managedIdentityPrincipalId, azureAiUserRoleId)
  scope: aiServicesAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource aiUserRoleOnProject 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(managedIdentityPrincipalId)) {
  name: guid(project.id, managedIdentityPrincipalId, azureAiUserRoleId)
  scope: project
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── App Insights Connection for Foundry Tracing ───────────────────────────
// Creates a connection from the AI Services account to Application Insights
// so that Foundry automatically captures server-side agent traces.
// Reference: https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/01-connections
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = if (!empty(appInsightsId)) {
  name: '${aiServicesAccountName}-appinsights'
  parent: aiServicesAccount
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}

output projectName string = project.name
output projectId string = project.id

// The project endpoint is constructed from the AI Services account endpoint.
// Format: https://<custom-subdomain>.services.ai.azure.com/api/projects/<project-name>
// The AIProjectClient from azure-ai-projects SDK uses this endpoint.
output projectEndpoint string = '${aiServicesAccount.properties.endpoint}api/projects/${projectName}'
