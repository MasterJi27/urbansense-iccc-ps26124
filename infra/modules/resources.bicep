targetScope = 'resourceGroup'

param name string
param location string
param tags object
param resourceSuffix string

var abbrName = toLower(replace('${name}${resourceSuffix}', '-', ''))
var kvName = take('kv${abbrName}', 24)
var stName = take('st${abbrName}', 24)
var planName = take('plan-${name}-${resourceSuffix}', 40)
var webName = take('app-${name}-${resourceSuffix}', 60)
var pgName = take('psql-${name}-${resourceSuffix}', 63)
var lawName = take('log-${name}-${resourceSuffix}', 63)
var appiName = take('appi-${name}-${resourceSuffix}', 255)

// Student-demo password: stored in Key Vault; rotate in portal after judging.
var postgresPassword = '${uniqueString(resourceGroup().id, 'pg')}Aa1!${resourceSuffix}'
var jwtSecret = '${uniqueString(resourceGroup().id, 'jwt')}${guid(resourceGroup().id)}'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: appiName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    IngestionMode: 'LogAnalytics'
  }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: pgName
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'urbansense'
    administratorLoginPassword: postgresPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'urbansense'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource postgresFw 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresExt 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'POSTGIS'
    source: 'user-override'
  }
}

var databaseUrl = 'postgresql+psycopg://urbansense:${postgresPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/urbansense?sslmode=require'

resource secretKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'secret-key'
  properties: { value: jwtSecret }
}

resource secretDb 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-url'
  properties: { value: databaseUrl }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  sku: { name: 'B1', tier: 'Basic' }
  kind: 'linux'
  properties: { reserved: true }
}

resource web 'Microsoft.Web/sites@2023-12-01' = {
  name: webName
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'python -m uvicorn app.main:app --host 0.0.0.0 --port 8000'
      healthCheckPath: '/health'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'APP_ENV', value: 'production' }
        { name: 'APP_NAME', value: 'UrbanSense' }
        { name: 'DEMO_SEED_ON_START', value: 'true' }
        { name: 'EVIDENCE_DIR', value: '/home/web_sierra/wwwroot/storage/evidence' }
        { name: 'PUBLIC_BASE_URL', value: 'https://${webName}.azurewebsites.net' }
        { name: 'CORS_ORIGINS', value: 'https://${webName}.azurewebsites.net' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appi.properties.ConnectionString }
        { name: 'AZURE_VISION_ENDPOINT', value: vision.properties.endpoint }
        { name: 'AZURE_STORAGE_ACCOUNT_URL', value: 'https://${storage.name}.blob.${environment().suffixes.storage}' }
        { name: 'AZURE_STORAGE_CONTAINER', value: 'evidence' }
        { name: 'AZURE_OPENAI_ENDPOINT', value: openai.properties.endpoint }
        { name: 'AZURE_OPENAI_DEPLOYMENT', value: 'gpt-4o-mini' }
        { name: 'AZURE_CONTENTSAFETY_ENDPOINT', value: safety.properties.endpoint }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'SECRET_KEY', value: '@Microsoft.KeyVault(SecretUri=${secretKey.properties.secretUri})' }
        { name: 'DATABASE_URL', value: '@Microsoft.KeyVault(SecretUri=${secretDb.properties.secretUri})' }
      ]
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource evidenceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'evidence'
  properties: { publicAccess: 'None' }
}

resource vision 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: take('cv${abbrName}', 24)
  location: location
  tags: tags
  kind: 'ComputerVision'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: take('cv${abbrName}', 24)
    publicNetworkAccess: 'Enabled'
  }
}

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: take('oai${abbrName}', 24)
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: take('oai${abbrName}', 24)
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource safety 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: take('cs${abbrName}', 24)
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: take('cs${abbrName}', 24)
    publicNetworkAccess: 'Enabled'
  }
}

var kvSecretsUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var blobContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var cognitiveUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var openaiUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')

resource webKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, web.id, kvSecretsUser)
  scope: kv
  properties: {
    roleDefinitionId: kvSecretsUser
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, web.id, blobContributor)
  scope: storage
  properties: {
    roleDefinitionId: blobContributor
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webVisionRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vision.id, web.id, cognitiveUser)
  scope: vision
  properties: {
    roleDefinitionId: cognitiveUser
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webOpenAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, web.id, openaiUser)
  scope: openai
  properties: {
    roleDefinitionId: openaiUser
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webSafetyRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(safety.id, web.id, cognitiveUser)
  scope: safety
  properties: {
    roleDefinitionId: cognitiveUser
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output apiUrl string = 'https://${web.properties.defaultHostName}'
output keyVaultName string = kv.name
output logAnalyticsId string = law.id
output storageName string = storage.name
output postgresName string = postgres.name
output visionEndpoint string = vision.properties.endpoint
output storageAccountUrl string = 'https://${storage.name}.blob.${environment().suffixes.storage}'
output openaiEndpoint string = openai.properties.endpoint
output safetyEndpoint string = safety.properties.endpoint
