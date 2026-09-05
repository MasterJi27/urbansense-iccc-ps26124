targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name')
param environmentName string

@minLength(1)
@description('Azure region for the resource group and most resources')
param location string

var resourceSuffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = {
  'azd-env-name': environmentName
  project: 'urbansense'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'modules/resources.bicep' = {
  name: 'urbansense-resources'
  scope: rg
  params: {
    name: environmentName
    location: location
    tags: tags
    resourceSuffix: resourceSuffix
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_KEY_VAULT_NAME string = resources.outputs.keyVaultName
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = resources.outputs.logAnalyticsId
output API_URL string = resources.outputs.apiUrl
output WEB_URL string = resources.outputs.apiUrl
output AZURE_VISION_ENDPOINT string = resources.outputs.visionEndpoint
output AZURE_STORAGE_ACCOUNT_URL string = resources.outputs.storageAccountUrl
output AZURE_OPENAI_ENDPOINT string = resources.outputs.openaiEndpoint
output AZURE_CONTENTSAFETY_ENDPOINT string = resources.outputs.safetyEndpoint
