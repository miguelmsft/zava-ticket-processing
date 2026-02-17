// ---------------------------------------------------------------------------
// Module: storage.bicep
// Creates: Storage Account + blob containers for PDFs and Functions
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Principal ID for RBAC role assignment (Managed Identity)')
param principalId string = ''

// Storage names: 3-24 chars, lowercase alphanumeric only
var cleanPrefix = replace(namingPrefix, '-', '')
var storageName = length('${cleanPrefix}stor') <= 24 ? '${cleanPrefix}stor' : take('${cleanPrefix}stor', 24)

// ── Storage Account ────────────────────────────────────────────────────────
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    // Allow public network access for Container Apps (no VNet integration in demo)
    publicNetworkAccess: 'Enabled'
  }
}

// ── Blob Service with CORS ─────────────────────────────────────────────────
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'PUT', 'POST', 'HEAD', 'OPTIONS']
          allowedHeaders: ['*']
          exposedHeaders: ['*']
          maxAgeInSeconds: 3600
        }
      ]
    }
  }
}

// ── Container: pdf-attachments ─────────────────────────────────────────────
resource pdfContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'pdf-attachments'
  properties: {
    publicAccess: 'None'
  }
}

// ── Container: invoices (used by backend for PDF uploads) ──────────────────
resource invoicesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'invoices'
  properties: {
    publicAccess: 'None'
  }
}

// ── RBAC: Storage Blob Data Contributor ────────────────────────────────────
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storageAccount.id, principalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Storage Blob Delegator (for User Delegation SAS) ────────────────
resource storageBlobDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storageAccount.id, principalId, 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output storageAccountName string = storageAccount.name
output storageAccountId string = storageAccount.id
output storageBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob

#disable-next-line outputs-should-not-contain-secrets
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
