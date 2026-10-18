param location string = resourceGroup().location
param projectName string = 'auditsys-ai'
param frontendImage string
param backendImage string
param allowedOrigins string = 'https://example.com'

// Non-secret configuration, passed as plain environment variables.
param supabaseUrl string
param azureOpenaiEndpoint string
param azureOpenaiDeployment string = 'gpt-4o'
param azureOpenaiEmbeddingDeployment string = 'text-embedding-3-large'
param azureOpenaiApiVersion string = '2024-02-01'
param adminUserIds string = ''

// Secrets are deployed INTO Key Vault and referenced by the container apps
// via managed identity — no secret ever lives in the container definition,
// a deployment log, or a plain-text env var.
@secure()
param supabaseServiceKey string

@secure()
param supabaseJwtSecret string

@secure()
param azureOpenaiApiKey string

@secure()
param redisUrl string

var acrName = replace('${projectName}acr', '-', '')
var keyVaultName = '${take(replace(projectName, '-', ''), 15)}${uniqueString(resourceGroup().id)}kv'
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${projectName}-identity'
  location: location
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Let the container apps' managed identity READ secrets from the vault.
resource identitySecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(managedIdentity.id, keyVault.id, secretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource supabaseServiceKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'supabase-service-key'
  properties: {
    value: supabaseServiceKey
  }
}

resource supabaseJwtSecretSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'supabase-jwt-secret'
  properties: {
    value: supabaseJwtSecret
  }
}

resource azureOpenaiApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-openai-api-key'
  properties: {
    value: azureOpenaiApiKey
  }
}

resource redisUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'redis-url'
  properties: {
    value: redisUrl
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${projectName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${projectName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var backendSecrets = [
  {
    name: 'supabase-service-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-service-key'
    identity: managedIdentity.id
  }
  {
    name: 'supabase-jwt-secret'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-jwt-secret'
    identity: managedIdentity.id
  }
  {
    name: 'azure-openai-api-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/azure-openai-api-key'
    identity: managedIdentity.id
  }
  {
    name: 'redis-url'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/redis-url'
    identity: managedIdentity.id
  }
]

resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${projectName}-api'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: backendSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          env: [
            {
              name: 'ALLOWED_ORIGINS'
              value: allowedOrigins
            }
            {
              name: 'SUPABASE_URL'
              value: supabaseUrl
            }
            {
              name: 'SUPABASE_SERVICE_KEY'
              secretRef: 'supabase-service-key'
            }
            {
              name: 'SUPABASE_JWT_SECRET'
              secretRef: 'supabase-jwt-secret'
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenaiEndpoint
            }
            {
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'azure-openai-api-key'
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: azureOpenaiDeployment
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
              value: azureOpenaiEmbeddingDeployment
            }
            {
              name: 'AZURE_OPENAI_API_VERSION'
              value: azureOpenaiApiVersion
            }
            {
              name: 'REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'ADMIN_USER_IDS'
              value: adminUserIds
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
  dependsOn: [
    identitySecretsUser
    supabaseServiceKeySecret
    supabaseJwtSecretSecret
    azureOpenaiApiKeySecret
    redisUrlSecret
  ]
}

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${projectName}-web'
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'web'
          image: frontendImage
          env: [
            {
              name: 'NEXT_PUBLIC_API_BASE_URL'
              value: 'https://${backend.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'NEXT_PUBLIC_SUPABASE_URL'
              value: supabaseUrl
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
}

output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output backendUrl string = 'https://${backend.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = keyVault.name
