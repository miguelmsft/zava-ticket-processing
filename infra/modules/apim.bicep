// ---------------------------------------------------------------------------
// Module: apim.bicep
// Creates: Azure API Management (BasicV2) — AI Gateway for MCP + OpenAPI tools
//
// ⚠️  APIM BasicV2 takes 30-45 minutes to provision.
//     For initial demo setup, you can skip this module (set deployApim=false
//     in main.bicep) and have agents call Azure Functions directly.
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Publisher email for APIM')
param publisherEmail string = 'admin@zavaprocessing.com'

@description('MCP Cosmos Function App URL')
param mcpCosmosUrl string = ''

@description('Code Mapping API Function App URL')
param codeMappingApiUrl string = ''

@description('Payment API Function App URL')
param paymentApiUrl string = ''

@description('Application Insights instrumentation key')
param appInsightsInstrumentationKey string = ''

// ── API Management Instance ────────────────────────────────────────────────
resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: '${namingPrefix}-apim'
  location: location
  tags: tags
  sku: {
    name: 'BasicV2'
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: 'Zava Processing Inc.'
  }
}

// ── Application Insights Logger ────────────────────────────────────────────
resource apimLogger 'Microsoft.ApiManagement/service/loggers@2023-09-01-preview' = if (!empty(appInsightsInstrumentationKey)) {
  parent: apim
  name: 'app-insights-logger'
  properties: {
    loggerType: 'applicationInsights'
    credentials: {
      instrumentationKey: appInsightsInstrumentationKey
    }
  }
}

// ── API: Code Mapping ──────────────────────────────────────────────────────
resource codeMappingApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = if (!empty(codeMappingApiUrl)) {
  parent: apim
  name: 'code-mapping-api'
  properties: {
    displayName: 'Code Mapping API'
    description: 'Reference code lookups for vendor, product, department, and action codes'
    path: 'codes'
    protocols: ['https']
    serviceUrl: codeMappingApiUrl
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

// ── API: Payment Processing ────────────────────────────────────────────────
resource paymentApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = if (!empty(paymentApiUrl)) {
  parent: apim
  name: 'payment-processing-api'
  properties: {
    displayName: 'Payment Processing API'
    description: 'Simulated payment validation and submission'
    path: 'payments'
    protocols: ['https']
    serviceUrl: paymentApiUrl
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

// ── API: MCP Cosmos DB Server ──────────────────────────────────────────────
// MCP endpoint exposed via APIM for Foundry Agent tool calls
resource mcpCosmosApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = if (!empty(mcpCosmosUrl)) {
  parent: apim
  name: 'mcp-cosmos-server'
  properties: {
    displayName: 'Cosmos DB MCP Server'
    description: 'MCP server for ticket CRUD operations via Foundry Agent tools'
    path: 'mcp/cosmos'
    protocols: ['https']
    serviceUrl: '${mcpCosmosUrl}/runtime/webhooks/mcp'
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

// ── Global Policy: Rate Limiting + CORS ────────────────────────────────────
resource apimPolicy 'Microsoft.ApiManagement/service/policies@2023-09-01-preview' = {
  parent: apim
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''
<policies>
  <inbound>
    <cors allow-credentials="true">
      <allowed-origins>
        <origin>*</origin>
      </allowed-origins>
      <allowed-methods>
        <method>*</method>
      </allowed-methods>
      <allowed-headers>
        <header>*</header>
      </allowed-headers>
    </cors>
    <rate-limit calls="100" renewal-period="60" />
  </inbound>
  <backend>
    <forward-request />
  </backend>
  <outbound />
  <on-error />
</policies>
'''
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output apimName string = apim.name
output apimGatewayUrl string = apim.properties.gatewayUrl
output apimId string = apim.id
