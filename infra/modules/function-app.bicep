// ---------------------------------------------------------------------------
// Module: function-app.bicep
// Creates: A single Azure Function App (Linux, Python 3.12) on a shared plan
// Reusable module — called once per function app from main.bicep
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Short name for this function (e.g., mcp-cosmos, api-payment)')
param functionName string

@description('azd service name tag value')
param serviceName string

@description('Resource ID of the shared App Service Plan')
param appServicePlanId string

@description('Storage account connection string for AzureWebJobsStorage')
@secure()
param storageConnectionString string

@description('Application Insights connection string')
param appInsightsConnectionString string

@description('User-Assigned Managed Identity resource ID')
param managedIdentityId string

@description('Managed Identity client ID')
param managedIdentityClientId string

@description('Additional app settings specific to this function')
param extraAppSettings array = []

var fullName = '${namingPrefix}-func-${functionName}'

// ── Base app settings (shared across all function apps) ────────────────────
var baseAppSettings = [
  { name: 'AzureWebJobsStorage', value: storageConnectionString }
  { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
  { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
  { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
  { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
  { name: 'ENABLE_ORYX_BUILD', value: 'true' }
  { name: 'AzureWebJobsFeatureFlags', value: 'EnableWorkerIndexing' }
  { name: 'PYTHON_ENABLE_GUNICORN_MULTIWORKERS', value: 'true' }
  { name: 'AzureWebJobsSecretStorageType', value: 'files' }
  { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '600' }
]

// ── Function App ───────────────────────────────────────────────────────────
resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: fullName
  location: location
  tags: union(tags, { 'azd-service-name': serviceName })
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlanId
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      appSettings: concat(baseAppSettings, extraAppSettings)
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
    }
    httpsOnly: true
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output functionAppId string = functionApp.id
