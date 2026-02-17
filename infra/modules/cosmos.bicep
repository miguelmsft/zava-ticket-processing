// ---------------------------------------------------------------------------
// Module: cosmos.bicep
// Creates: Azure Cosmos DB for NoSQL (Serverless) + database + 3 containers
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Principal ID for RBAC role assignment (Managed Identity)')
param principalId string = ''

var accountName = '${namingPrefix}-cosmos'
var databaseName = 'zava-ticket-processing'

// ── Cosmos DB Account (Serverless) ─────────────────────────────────────────
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      { name: 'EnableServerless' }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    // Disable key-based auth in production; use RBAC via Managed Identity
    disableLocalAuth: false
    // Allow public network access for Container Apps (no VNet integration in demo)
    publicNetworkAccess: 'Enabled'
  }
}

// ── Database ───────────────────────────────────────────────────────────────
resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ── Container: tickets (PK: /ticketId) ─────────────────────────────────────
resource ticketsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'tickets'
  properties: {
    resource: {
      id: 'tickets'
      partitionKey: {
        paths: ['/ticketId']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
      }
    }
  }
}

// ── Container: code-mappings (PK: /mappingType) ────────────────────────────
resource codeMappingsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'code-mappings'
  properties: {
    resource: {
      id: 'code-mappings'
      partitionKey: {
        paths: ['/mappingType']
        kind: 'Hash'
      }
    }
  }
}

// ── Container: metrics (PK: /metricType) ───────────────────────────────────
resource metricsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'metrics'
  properties: {
    resource: {
      id: 'metrics'
      partitionKey: {
        paths: ['/metricType']
        kind: 'Hash'
      }
    }
  }
}

// ── RBAC: Cosmos DB Built-in Data Contributor ──────────────────────────────
// Role ID: 00000000-0000-0000-0000-000000000002
resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, principalId, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: principalId
    scope: cosmosAccount.id
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output cosmosAccountName string = cosmosAccount.name
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
output cosmosDatabaseName string = databaseName
output cosmosAccountId string = cosmosAccount.id
