// ---------------------------------------------------------------------------
// Module: container-registry.bicep
// Creates: Azure Container Registry (Basic) for backend Docker images
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources (minimum 3 chars)')
@minLength(3)
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Principal ID for RBAC role assignment (Managed Identity)')
param principalId string = ''

// ACR names: 5-50 chars, alphanumeric only
var cleanPrefix = replace(namingPrefix, '-', '')
var acrName = '${cleanPrefix}registry'

// ── Container Registry ─────────────────────────────────────────────────────
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true // Required for Container Apps pull; use managed identity in production
  }
}

// ── RBAC: AcrPull ──────────────────────────────────────────────────────────
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(containerRegistry.id, principalId, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output acrName string = containerRegistry.name
output acrLoginServer string = containerRegistry.properties.loginServer
output acrId string = containerRegistry.id
