// ---------------------------------------------------------------------------
// Module: app-service-plan.bicep
// Creates: A shared Linux App Service Plan (B2) for all Azure Function Apps
// ---------------------------------------------------------------------------
// NOTE: Uses B2 (Basic, 2 cores, 3.5 GB RAM) because the azure-ai-projects
// SDK is heavy and B1 caused cold-start timeouts.
// Requires "Basic VMs" App Service quota in the target region.
// In production, upgrade to P1v3 or EP1 (Elastic Premium) for auto-scale.
// ---------------------------------------------------------------------------

@description('Azure region for all resources')
param location string

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

// Shared B2 Linux App Service Plan for all function apps.
// B2 required for heavy Python functions (azure-ai-projects SDK); B1 caused cold-start timeouts.
// In production, upgrade to P1v3 or EP1 (Elastic Premium) for auto-scale.
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namingPrefix}-func-plan'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    // B2 (Basic): 2 cores, 3.5 GB RAM — needed for heavy Python functions (azure-ai-projects SDK).
    // B1 caused cold-start timeouts. In production, upgrade to P1v3 or EP1 for auto-scale.
    // NOTE: Requires "Basic VMs" quota in the target region. Request via https://aka.ms/antquotahelp
    name: 'B2'
    tier: 'Basic'
  }
  properties: {
    reserved: true // Required for Linux
  }
}

output planId string = appServicePlan.id
output planName string = appServicePlan.name
