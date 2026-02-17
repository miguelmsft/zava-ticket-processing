// ---------------------------------------------------------------------------
// Module: container-apps.bicep
// Creates: Container Apps Environment + Backend Container App (FastAPI)
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Log Analytics workspace name (must exist in same resource group)')
param logAnalyticsWorkspaceName string

@description('ACR login server (e.g., myacr.azurecr.io)')
param acrLoginServer string

@description('User-Assigned Managed Identity resource ID')
param managedIdentityId string

@description('Managed Identity client ID for DefaultAzureCredential')
param managedIdentityClientId string

@description('Cosmos DB endpoint URL')
param cosmosEndpoint string

@description('Cosmos DB database name')
param cosmosDatabaseName string

@description('Blob Storage endpoint URL')
param storageBlobEndpoint string

@description('Storage account name')
param storageAccountName string

@description('Application Insights connection string')
param appInsightsConnectionString string

@description('Stage B Azure Function URL')
param stageBFunctionUrl string = ''

@description('Stage C Azure Function URL')
param stageCFunctionUrl string = ''

@description('Stage B Azure Function key')
@secure()
param stageBFunctionKey string = ''

@description('Stage C Azure Function key')
@secure()
param stageCFunctionKey string = ''

@description('Azure AI Services endpoint (for Content Understanding)')
param aiServicesEndpoint string = ''

@description('Content Understanding completion model deployment name')
param cuModelDeploymentName string = 'gpt-4.1'

@description('Content Understanding embeddings model deployment name')
param embeddingsDeploymentName string = 'text-embedding-3-large'

@description('Frontend URL for CORS (Static Web App URL)')
param frontendUrl string = ''

// ── Reference existing Log Analytics workspace ─────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

// ── Container Apps Environment ─────────────────────────────────────────────
resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namingPrefix}-cae'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        #disable-next-line use-secure-value-for-secure-inputs
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── Backend Container App ──────────────────────────────────────────────────
resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namingPrefix}-backend'
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          // Initial placeholder image; azd deploy will replace with the built image
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DATABASE_NAME', value: cosmosDatabaseName }
            { name: 'AZURE_STORAGE_BLOB_ENDPOINT', value: storageBlobEndpoint }
            { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'STAGE_B_FUNCTION_URL', value: stageBFunctionUrl }
            { name: 'STAGE_C_FUNCTION_URL', value: stageCFunctionUrl }
            { name: 'STAGE_B_FUNCTION_KEY', value: stageBFunctionKey }
            { name: 'STAGE_C_FUNCTION_KEY', value: stageCFunctionKey }
            { name: 'DISABLE_SIMULATION_FALLBACK', value: 'true' }
            { name: 'AZURE_AI_ENDPOINT', value: aiServicesEndpoint }
            { name: 'CU_MODEL_DEPLOYMENT_NAME', value: cuModelDeploymentName }
            { name: 'CU_EMBEDDINGS_DEPLOYMENT_NAME', value: embeddingsDeploymentName }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'CORS_ORIGINS', value: 'http://localhost:5173,http://localhost:3000,${frontendUrl}' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 5
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output containerAppsEnvironmentId string = containerAppsEnvironment.id
output backendFqdn string = backendApp.properties.configuration.ingress.fqdn
output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output backendName string = backendApp.name
