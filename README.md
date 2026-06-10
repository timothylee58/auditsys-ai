# AuditSys AI

AuditSys AI is a starter full-stack audit assistant for document ingestion, evidence-grounded querying, reviewer queues, immutable audit logs, and evaluation dashboards.

## Stack

- Frontend: Next.js 15, React, TypeScript, Tailwind CSS
- Backend: FastAPI, Pydantic, Python 3.12
- Local services: PostgreSQL, Redis
- Deployment target: Azure Container Apps with Azure Container Registry

## Local Development

```powershell
Copy-Item .env.example .env
npm install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\backend[dev]
npm run dev
```

In another terminal:

```powershell
.\.venv\Scripts\Activate.ps1
npm run api
```

Frontend runs at `http://localhost:3000`; API runs at `http://localhost:8000`.

## Docker

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

## Azure Deployment

The Bicep template in `infra/azure/main.bicep` provisions an Azure Container Apps environment, ACR, Log Analytics, and frontend/backend container apps. Build and push images to ACR, then deploy the template with the image tags.

## Netlify Deployment

The frontend is configured for Netlify through `netlify.toml`.

Recommended Netlify flow:

```powershell
npm install
npm run build --workspace frontend
netlify deploy --build
```

Set `NEXT_PUBLIC_API_BASE_URL` in Netlify environment variables to your deployed Azure Container Apps API URL.
