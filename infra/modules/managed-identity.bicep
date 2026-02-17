// ---------------------------------------------------------------------------
// Module: managed-identity.bicep
// Creates: User-Assigned Managed Identity for cross-service authentication
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

// ── User-Assigned Managed Identity ─────────────────────────────────────────
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namingPrefix}-identity'
  location: location
  tags: tags
}

// ── Outputs ────────────────────────────────────────────────────────────────
output managedIdentityId string = managedIdentity.id
output managedIdentityClientId string = managedIdentity.properties.clientId
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output managedIdentityName string = managedIdentity.name
