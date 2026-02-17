// ---------------------------------------------------------------------------
// Module: static-web-app.bicep
// Creates: Azure Static Web App (Free tier) for React frontend
// ---------------------------------------------------------------------------

@description('Azure region for all resources (fallback)')
param location string

@description('SWA-specific region override. SWA only supports: westus2, centralus, eastus2, westeurope, eastasia')
param swaLocation string = ''

@description('Naming prefix for resources')
param namingPrefix string

@description('Tags to apply to all resources')
param tags object = {}

@description('Backend API URL for SWA linked backend (used with Standard tier)')
#disable-next-line no-unused-params
param backendUrl string = ''

// ── Static Web App ─────────────────────────────────────────────────────────
// Use swaLocation if provided, otherwise fall back to main location
var effectiveSwaLocation = !empty(swaLocation) ? swaLocation : location

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${namingPrefix}-frontend'
  location: effectiveSwaLocation
  tags: union(tags, { 'azd-service-name': 'frontend' })
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    // Build configuration is handled by azd deploy, not ARM
  }
}

// ── Linked Backend (routes /api/* to Container App) ────────────────────────
// Note: This links the SWA to the backend Container App so that
// /api/* requests are proxied automatically. Requires Standard tier.
// For Free tier, configure CORS on the backend instead.
// resource linkedBackend 'Microsoft.Web/staticSites/linkedBackends@2023-12-01' = if (!empty(backendUrl)) {
//   parent: staticWebApp
//   name: 'backend'
//   properties: {
//     backendResourceId: backendUrl
//     region: location
//   }
// }

// ── Outputs ────────────────────────────────────────────────────────────────
output staticWebAppName string = staticWebApp.name
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output staticWebAppId string = staticWebApp.id
