# Zava Processing Inc. — AI Ticket Processing System

An AI-powered ticket processing pipeline that automates invoice extraction, validation, and payment for **Zava Processing Inc.**, a fictional industrial processing company.

Built on Azure with Python, FastAPI, Azure Cosmos DB, and Azure AI services.

---

## What It Does

Tickets arrive (simulating a Salesforce integration), and the system automatically:

1. **Extracts** structured data from attached PDF invoices (vendor, amounts, line items, dates)
2. **Processes** the data with AI agents that standardize codes, summarize, and assign actions
3. **Validates & pays** invoices through an automated payment pipeline
4. **Displays** the entire workflow in a 5-tab real-time UI

---

## Architecture Overview

```
Ticket (PDF) → FastAPI Backend → Extraction Pipeline → Cosmos DB
                                       │
                           ┌───────────┴───────────┐
                           │                       │
                     PyMuPDF (local)     Invoice Data Extraction
                     Basic metadata      (user selects method):
                     (always runs)       • Python Regex (~40ms)
                                         • Azure Content Understanding (~30s)
```

For the full architecture, see [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md).

---

## Pipeline Trigger Flow

The processing pipeline has four stages. In the **demo**, stages are triggered via the UI so the audience can see each step. In **production**, the entire pipeline runs automatically end-to-end.

### How each stage is triggered

```
┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Salesforce   │────▶│  Stage A    │────▶│  Stage B    │────▶│  Stage C    │
│  New Ticket   │     │  Extraction │     │  AI Process │     │  Invoice    │
└──────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
     trigger:             trigger:            trigger:            trigger:
  webhook / event     automatic (inline)   HTTP POST call     HTTP POST call
```

| Stage | What triggers it | Demo behavior | Production behavior |
|-------|-----------------|---------------|-------------------|
| **Salesforce → System** | A new ticket is created in Salesforce | User fills out the "Ticket Ingestion" form in the UI and clicks Submit | Salesforce fires a **Platform Event** or **Outbound Message** (webhook) to the backend `POST /api/tickets` endpoint. Alternatively, an **Azure Logic App** with the Salesforce connector polls for new cases and forwards them. |
| **Stage A — Extraction** | `POST /api/tickets` is called | Runs automatically — as soon as the ticket is submitted, extraction starts as a `BackgroundTask` in the FastAPI process | Same — runs inline. For higher throughput, extraction could be offloaded to an **Azure Function** triggered by a **Service Bus queue** to handle parallel processing of thousands of concurrent tickets. |
| **Stage B — AI Processing** | Ticket reaches `extracted` status | User clicks **"Process with AI"** button in the Extraction Results tab, which calls `POST /api/tickets/{id}/process-ai` | **Cosmos DB Change Feed** trigger. When Stage A writes `status: "extracted"` to Cosmos DB, a Change Feed–triggered Azure Function automatically fires Stage B. No human action needed. |
| **Stage C — Invoice Processing** | Ticket reaches `ai_processed` status | User clicks **"Process Invoice"** button in the AI Processing Results tab, which calls `POST /api/tickets/{id}/process-invoice` | **Cosmos DB Change Feed** trigger. When Stage B writes `status: "ai_processed"`, a Change Feed–triggered Azure Function automatically fires Stage C. |

### Why the demo uses manual triggers

The demo intentionally pauses between stages so the audience can:
1. **See extraction results** before AI processing runs
2. **Inspect AI outputs** (standardized codes, summary, next action) before invoice processing
3. **Follow the data** as it moves through each stage in the UI tabs

In production, the entire flow from Salesforce event to invoice payment completes automatically in seconds.

### Production architecture for Salesforce integration

```
Salesforce                    Azure
─────────                    ─────
                              
Case created ──▶ Platform Event / Outbound Message
                       │
                       ▼
                 Azure Logic App  (or API Management)
                 + Salesforce Connector
                       │
                       ▼
                 POST /api/tickets   ◀── Backend (Container App)
                       │
                       ▼
                 Stage A: Extraction  (BackgroundTask or Service Bus)
                       │
                       ▼  writes status: "extracted" to Cosmos DB
                       │
                 ┌─────┴─────┐
                 │ Change Feed│  ◀── Cosmos DB Change Feed Trigger
                 └─────┬─────┘
                       ▼
                 Stage B: AI Processing  (Azure Function)
                       │
                       ▼  writes status: "ai_processed" to Cosmos DB
                       │
                 ┌─────┴─────┐
                 │ Change Feed│  ◀── Cosmos DB Change Feed Trigger
                 └─────┬─────┘
                       ▼
                 Stage C: Invoice Processing  (Azure Function)
                       │
                       ▼  writes status: "completed" / "payment_submitted"
                       │
                 (Optional) Callback to Salesforce to update case status
```

**Key production additions:**
- **Azure Logic App** with the [Salesforce connector](https://learn.microsoft.com/en-us/connectors/salesforce/) to receive events from Salesforce without custom webhook code
- **Cosmos DB Change Feed triggers** to chain stages automatically — when a document's `status` field changes, the next stage fires within milliseconds
- **Azure Service Bus** for Stage A if extraction volume exceeds what a single `BackgroundTask` can handle (millions/week) — tickets are queued and processed by multiple Function instances in parallel
- **APIM (AI Gateway)** in front of MCP servers for rate limiting, auth, and observability at scale (scaffolded in infra but disabled for the demo)
- **Salesforce callback** — after Stage C completes, the system can call back to Salesforce to update the case status, close the ticket, or attach the payment confirmation

> **Note:** The demo's HTTP-trigger architecture (`POST /process-ai`, `POST /process-invoice`) was chosen intentionally — it is simpler to debug, easier to demo, and the same Azure Functions can be reused behind Change Feed triggers in production with minimal code changes (the Function body stays the same, only the trigger binding changes from `httpTrigger` to `cosmosDBTrigger`).

### Full demo vs. production comparison

Beyond the trigger flow, there are several other architectural differences between the demo and a production deployment. The table below summarizes every important distinction.

| Area | Demo (current) | Production | Why the demo differs |
|------|---------------|------------|---------------------|
| **Ticket source** | User fills a form in the React UI | Salesforce Platform Event / Outbound Message → Azure Logic App → `POST /api/tickets` | No Salesforce instance available for the demo |
| **Stage chaining** | Manual UI button clicks between stages | Cosmos DB Change Feed triggers fire automatically on status change | Pausing lets the audience inspect each step |
| **Data volume** | 6 sample tickets, one at a time | 4 million+ tickets/week, concurrent processing | Low volume keeps the demo fast and debuggable |
| **Database** | Azure Cosmos DB Serverless (auto-scale to zero) | Cosmos DB **Provisioned Throughput** with autoscale RU/s (or dedicated multi-region writes) | Serverless is cost-free when idle, perfect for a demo |
| **Storage fallback** | In-memory `dict` when Cosmos DB is not configured (`APP_ENV=development`) | Always Cosmos DB — no in-memory fallback | Lets developers run the full UI locally with zero Azure credentials |
| **PDF extraction** | User-selectable toggle: **Python Regex** (~40ms, default) or **Azure Content Understanding** (~30s). Both paths available; toggle on Tab 1 | Always **Azure Content Understanding** (prebuilt-invoice analyzer) with real confidence scores | Toggle lets demo audience compare extraction speeds; production always uses CU for accuracy |
| **AI agents** | Local simulation (`_simulate_ai_processing`) when Azure Functions / Foundry are unavailable | **Foundry Agent Service V2** (Responses API) with MCP tools — always active | Simulation keeps the demo functional without AI model quota |
| **Simulation fallback** | Backend auto-detects non-200 responses from Azure Functions and falls back to local simulation with realistic demo data | No fallback — all functions always available on Premium plan | Ensures demo works even when Functions have cold-start issues on shared B1 plan |
| **Payment system** | Simulated payment API (`api_payment` Function) that accepts all invoices and returns fake confirmation IDs | Real ERP / payment gateway integration (SAP, Oracle, custom AP system) | No real payment system to connect to |
| **Payment callback** | None — pipeline ends at `completed` status | System calls back to Salesforce to update case status and attach payment confirmation | No Salesforce instance to call back to |
| **Blob storage** | PDF upload skipped when `BLOB_CONNECTION_STRING` is empty; PDF bytes held in memory only | Always **Azure Blob Storage** with SAS URLs for Content Understanding | Demo runs without a storage account |
| **Authentication** | No auth — all API endpoints are open. Backend uses **Managed Identity** (`DefaultAzureCredential`) for Cosmos DB and Blob Storage | Azure AD / Entra ID with Managed Identity; API keys for Function-to-Function calls; OAuth for Salesforce | Simplifies demo setup and debugging |
| **API gateway (APIM)** | Disabled (`deployApim = false` in Bicep); agents call MCP server directly via Function URL | **Azure API Management (AI Gateway)** in front of all MCP servers for rate limiting, token auth, caching, and observability | APIM takes 30–45 min to provision; not needed for demo |
| **MCP server access** | Agents call MCP Azure Function directly via URL | Agents call MCP through APIM AI Gateway endpoint | Direct calls are simpler; APIM adds governance at scale |
| **Compute plan** | Shared **B2 Linux** App Service Plan for all 5 Function Apps | **Consumption (Y1)** or **Premium (EP1+)** plan per function app for elastic scale-to-zero and scale-out | B2 used because the demo subscription lacks Consumption VM quota |
| **Backend scaling** | Container App: min 0, max 5 replicas, 0.5 vCPU / 1 GiB per replica | Container App: min 1, max 50+ replicas, 2+ vCPU / 4+ GiB, multiple revisions | Demo scale is minimal to control cost |
| **Frontend hosting** | Azure Static Web Apps **Free** tier | Static Web Apps **Standard** tier with custom domain, linked backend, and enterprise-grade SLA | Free tier is sufficient for a demo |
| **Observability** | Application Insights + Log Analytics — built-in telemetry via `APPLICATIONINSIGHTS_CONNECTION_STRING` (requests, dependencies, traces all flow automatically; see [Microsoft docs](https://learn.microsoft.com/azure/azure-monitor/app/monitor-functions)) | App Insights + Log Analytics + **Azure Monitor alerts**, **dashboards**, and **distributed tracing** across all services | Built-in App Insights integration is sufficient for the demo — no SDK packages needed ([learn more](https://learn.microsoft.com/azure/azure-functions/functions-monitoring)) |
| **Multi-region** | Single region (Sweden Central) | **Multi-region** Cosmos DB with automatic failover; Container Apps in multiple regions behind Azure Front Door | Demo doesn't need HA/DR |
| **CI/CD** | Manual deploy via `azd up` | **GitHub Actions** or **Azure DevOps** pipeline with staging slots, canary releases, automated tests | `azd up` is fastest for demo iteration |
| **Networking** | All services on public endpoints | **VNet integration**, private endpoints for Cosmos DB and Storage, WAF on Front Door | Simplifies demo setup |
| **Data samples** | 6 pre-generated PDFs with known outcomes (happy path, hazmat, discrepancy, past-due, multi-line, unapproved vendor) | Real customer invoices from Salesforce attachments | Generated data tells a clear demo story |
| **Error handling** | Basic try/catch with status `error` written to Cosmos DB | **Dead-letter queues** (Service Bus DLQ), retry policies, alerts on failure, manual review workflow | Demo shows the happy path; production must handle every edge case |
| **Concurrency** | Single `BackgroundTask` per ticket (sequential) | **Service Bus queues** + Azure Functions with configurable batch size and parallelism | `BackgroundTask` is sufficient for one-at-a-time demo flow |
| **Real-time updates** | Frontend polls backend every 3 seconds (`usePolling` hook) | **WebSockets** or **Server-Sent Events (SSE)** for instant UI updates; or Azure SignalR Service | Polling is simpler to implement and debug |

---

## What's Built

### Backend API (FastAPI on Azure Container Apps)

A FastAPI application with 15 routes:

| Endpoint | Description |
|---|---|
| `POST /api/tickets` | Submit a ticket with PDF attachment |
| `GET /api/tickets` | List tickets (paginated, filterable by status) |
| `GET /api/tickets/{id}` | Full ticket details |
| `GET /api/tickets/{id}/extraction` | Stage A extraction results |
| `GET /api/tickets/{id}/ai-processing` | Stage B AI results |
| `GET /api/tickets/{id}/invoice-processing` | Stage C invoice results |
| `POST /api/tickets/{id}/process-ai` | Trigger AI information processing |
| `POST /api/tickets/{id}/process-invoice` | Trigger invoice processing |
| `POST /api/tickets/{id}/reprocess` | Re-trigger the processing pipeline |
| `DELETE /api/tickets/{id}` | Delete a ticket |
| `GET /api/dashboard/metrics` | Aggregated processing metrics |
| `GET /health` | Health check with dependency status |

### Frontend UI (React + Vite + TypeScript on Azure Static Web Apps)

A 5-tab single-page application with real-time polling:

| Tab | Purpose |
|-----|--------|
| **Ticket Ingestion** | Submit tickets with auto-attaching sample PDFs, Salesforce feed simulation, extraction method toggle (Python Regex / Content Understanding) |
| **Extraction Results** | PDF metadata, invoice details, line items, confidence scores, extraction method badge |
| **AI Processing** | Standardized codes, AI summary, flags, next action routing |
| **Invoice Processing** | Validation checklist, payment submission status |
| **Dashboard** | Metrics cards, timing averages, pipeline chart, recent tickets |

### Azure Functions (5 function apps on shared B2 plan)

| Function | Purpose |
|----------|--------|
| `mcp-cosmos` | MCP server for Cosmos DB agent tool access |
| `stage-b` | AI Information Processing agent trigger |
| `stage-c` | Invoice Processing agent trigger |
| `api-code-mapping` | Code mapping lookup API |
| `api-payment` | Simulated payment processing API |

### PDF Extraction Pipeline

Every submitted ticket triggers a two-step extraction in the background:

#### Step 1 — PyMuPDF (always runs)

Extracts basic PDF metadata locally using [PyMuPDF](https://pymupdf.readthedocs.io/):

- Page count, file size, PDF creation date
- Raw text preview (first 2,000 characters)

#### Step 2 — Invoice Data Extraction (user-selectable method)

The user selects the extraction method via a toggle on Tab 1 before submitting a ticket. The default is **Python Regex** for instant results during the demo.

| Method | Speed | How it works | Confidence scores |
|---|---|---|---|
| **Python Regex** (default) | ~40ms | Parses raw text from Step 1 using regex patterns (`_extract_fallback()`) | Simulated (0.85–0.96) |
| **Content Understanding** | ~30s | Sends the PDF (via SAS URL) to Azure's **prebuilt-invoice** analyzer (`_extract_with_cu_sdk()`) | Real AI confidence (0.78–0.88) |

**Both paths extract the same fields:**
invoice number, vendor name/address, dates, PO number, subtotal, tax, total, payment terms, line items (description, product code, quantity, unit price, amount), and special flags (hazardous materials, DOT classification, bill of lading).

**Line item amount fix:** When Azure Content Understanding returns `0` for a line item amount, the system automatically computes `quantity × unitPrice`.

The extraction method used is displayed as a badge on Tab 2 (Extraction Results): ⚡ Python Regex (green) or 🧠 Content Understanding (violet).

### Data Layer

- **Azure Cosmos DB for NoSQL** — three containers:
  - `tickets` (partition key: `/ticketId`) — full pipeline documents
  - `code-mappings` (partition key: `/mappingType`) — vendor, product, department, action codes
  - `metrics` (partition key: `/metricType`) — dashboard aggregation
- **Azure Blob Storage** — PDF attachments stored as `{ticketId}/{filename}`

### Sample Data

Six realistic demo tickets with generated PDF invoices:

| Ticket | Vendor | Scenario | Total |
|---|---|---|---|
| ZAVA-2026-00001 | ABC Industrial Supplies | Happy path | $13,531.25 |
| ZAVA-2026-00002 | Delta Chemical Solutions | Hazardous materials, urgent | $1,560.42 |
| ZAVA-2026-00003 | Pinnacle Precision Parts | Amount discrepancy | $8,248.50 |
| ZAVA-2026-00004 | Summit Electrical Corp | Past-due invoice | $2,692.28 |
| ZAVA-2026-00005 | Oceanic Freight Logistics | Complex multi-line, international | $20,900.00 |
| ZAVA-2026-00006 | Greenfield Environmental | Unapproved vendor | $14,045.44 |

---

## Project Structure

```
├── architecture/                    # Architecture documents & interactive diagrams
│   ├── ARCHITECTURE.md              # System architecture document
│   ├── architecture_diagram.html    # Interactive Demo & Production architecture diagrams
│   └── icons/                       # Azure service icons (SVG + PNG)
├── PLAN.md                      # Detailed implementation plan
├── README.md                    # This file
├── azure.yaml                   # Azure Developer CLI service manifest
│
├── backend/                     # FastAPI backend (Container Apps)
│   ├── app/
│   │   ├── main.py              # FastAPI app with lifespan, CORS, health
│   │   ├── config.py            # pydantic-settings configuration
│   │   ├── models/ticket.py     # 20+ Pydantic models (enums, stages, API)
│   │   ├── routers/             # tickets.py, dashboard.py
│   │   └── services/            # cosmos_client, blob_storage, extraction,
│   │                            # ai_processing, invoice_processing
│   ├── tests/                   # 139 backend tests
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                    # React + Vite + TypeScript (Static Web Apps)
│   ├── src/
│   │   ├── App.tsx              # 5-tab layout with state management
│   │   ├── components/tabs/     # TicketIngestion, ExtractionResults,
│   │   │                        # AIProcessingResults, InvoiceProcessing, Dashboard
│   │   ├── services/api.ts      # API client with error handling
│   │   ├── hooks/usePolling.ts  # Polling hook for real-time updates
│   │   ├── data/sampleTickets.ts # 6 demo ticket presets
│   │   └── __tests__/           # 55 frontend tests
│   ├── .env.production          # Production API base URL
│   └── vite.config.ts           # Dev server proxy + Vitest config
│
├── functions/                   # 5 Azure Function apps
│   ├── mcp_cosmos/              # MCP server for Cosmos DB
│   ├── stage_b_ai_processing/   # AI Processing agent trigger
│   ├── stage_c_invoice_processing/ # Invoice Processing agent trigger
│   ├── api_code_mapping/        # Code mapping lookup
│   ├── api_payment/             # Simulated payment API
│   ├── openapi/                 # OpenAPI specs for code mapping & payment APIs
│   └── tests/                   # 127 function tests
│
├── infra/                       # Bicep IaC templates
│   ├── main.bicep               # Orchestrator (16+ resources)
│   └── modules/                 # container-app, function-app, cosmos-db,
│                                # ai-services, app-service-plan, etc.
│
├── scripts/                     # Deployment & seed scripts
│   ├── acr_deploy.ps1           # ACR container image deployment
│   ├── deploy.ps1               # Interactive deployment (Windows)
│   ├── deploy.sh                # Interactive deployment (Linux/Mac)
│   └── postdeploy.py            # Cosmos DB seeder + health checks
│
├── data/
│   ├── sample_tickets.json      # 6 demo tickets with expected outcomes
│   ├── code_mappings.json       # Vendor, product, department, action codes
│   ├── generate_sample_pdf.py   # Script to regenerate PDFs (reportlab)
│   └── sample_pdfs/             # 6 generated invoice PDFs
│
└── docs/
    ├── DEMO_FLOW.md             # Step-by-step demo walkthrough
    └── MAF_Foundry_V1_vs_V2.md  # Foundry V1 vs V2 comparison research
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Azure Cosmos DB account (or [emulator](https://learn.microsoft.com/azure/cosmos-db/emulator))
- Azure Blob Storage account *(optional — uploads are skipped if not configured)*
- Azure Content Understanding resource *(optional — falls back to regex)*

### Setup

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Azure credentials

# Frontend
cd frontend
npm install
```

### Run Locally (Development)

```bash
# Terminal 1: Backend
cd backend
$env:APP_ENV="development"  # PowerShell
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

The API is available at `http://localhost:8000` (docs at `/docs`).  
The frontend is available at `http://localhost:5173`.

> **Note:** In development mode (`APP_ENV=development`), the system uses in-memory storage and local simulation for AI agents — no Azure credentials required.

### Run Tests

```bash
# Backend (139 tests)
cd backend && python -m pytest tests/ -q

# Frontend (55 tests)
cd frontend && npx vitest run

# Functions (127 tests)
python -m pytest functions/ -q

# Total: 321 tests
```

### Deploy to Azure

Uses [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/):

```bash
azd auth login
azd up                          # Provision infrastructure + deploy all services
```

The CLI will prompt you for:
- **Environment name** — used for the resource group (`rg-<name>`) and service naming
- **Azure region** — `eastus2`, `swedencentral`, or `westus3`
- **Naming prefix** — short prefix for all Azure resource names (e.g., `zavatktpr`)

All resource names are derived from the naming prefix you choose, so each deployment is unique.

> **Automatic RBAC:** A `preprovision` hook auto-detects your Azure AD identity and grants you the `Azure AI User` role on the AI Services resource, so you can view and manage Foundry V2 agents in the [portal](https://ai.azure.com) immediately after deployment.

To redeploy a single service after code changes:

```bash
azd deploy backend --no-prompt   # Deploy just the backend (fastest)
azd deploy frontend --no-prompt  # Deploy just the frontend
azd deploy stage-b --no-prompt   # Deploy a specific function app
```

> **Tip:** Deploying services individually is more reliable than `azd deploy --no-prompt` (all at once), especially in PowerShell 5.1.

---

## Configuration

All settings are read from environment variables (see `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `AZURE_COSMOS_ENDPOINT` | Yes | Cosmos DB account URI (also accepts `COSMOS_ENDPOINT` or `COSMOS_DB_ENDPOINT`) |
| `AZURE_CLIENT_ID` | No | User-Assigned Managed Identity client ID (used for Cosmos DB + Blob auth when no keys are set) |
| `COSMOS_DB_KEY` | No | Cosmos DB primary key (not needed when using Managed Identity) |
| `COSMOS_DATABASE_NAME` | No | Database name (default: `zava-ticket-processing`; also accepts `COSMOS_DB_DATABASE`) |
| `AZURE_STORAGE_BLOB_ENDPOINT` | No | Blob Storage endpoint (used with MI auth; also accepts `BLOB_CONNECTION_STRING`) |
| `BLOB_CONTAINER_NAME` | No | Container name (default: `invoices`) |
| `CONTENT_UNDERSTANDING_ENDPOINT` | No | Enables cloud AI extraction |
| `CONTENT_UNDERSTANDING_KEY` | No | Content Understanding API key |
| `STAGE_B_FUNCTION_URL` | No | Stage B Azure Function URL (auto-appends `/api/process-ticket` if missing) |
| `STAGE_C_FUNCTION_URL` | No | Stage C Azure Function URL (auto-appends `/api/process-invoice` if missing) |
| `CORS_ORIGINS` | No | Allowed CORS origins (comma-separated; also accepts `ALLOWED_ORIGINS`) |
| `APP_ENV` | No | `development` for in-memory storage, `production` for Cosmos DB |

When optional services are not configured, the system falls back gracefully — blob uploads are skipped, extraction uses the regex parser, and AI/invoice processing uses local simulation.

> **Note:** In the Azure deployment, the backend uses **User-Assigned Managed Identity** for Cosmos DB and Blob Storage authentication (no keys stored in environment variables). The `AZURE_CLIENT_ID` environment variable is set automatically by the Bicep infrastructure templates.

---

## Technology Stack

| Component | Technology |
|---|---|
| Backend API | Python, FastAPI, Uvicorn |
| Frontend UI | React, Vite, TypeScript, Tailwind CSS |
| Database | Azure Cosmos DB for NoSQL |
| PDF Storage | Azure Blob Storage |
| PDF Metadata | PyMuPDF (fitz) |
| Invoice Extraction | Azure Content Understanding (prebuilt-invoice) |
| Extraction Fallback | Regex parser on PyMuPDF text output |
| AI Agents | Foundry Agent Service V2 (azure-ai-projects) |
| AI Gateway | Azure API Management (MCP servers) |
| Backend Hosting | Azure Container Apps |
| Frontend Hosting | Azure Static Web Apps |
| Event Triggers | Azure Functions (5 apps, B2 plan) |
| Infrastructure | Bicep IaC via Azure Developer CLI |
| AI Models | GPT-5-mini, GPT-4.1, text-embedding-3-large |
| Configuration | pydantic-settings, python-dotenv |
| Containerization | Docker |

---

## Documentation

| Document | Description |
|----------|------------|
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | System architecture with diagrams |
| [docs/DEMO_FLOW.md](docs/DEMO_FLOW.md) | Step-by-step demo walkthrough |
| [docs/MAF_Foundry_V1_vs_V2.md](docs/MAF_Foundry_V1_vs_V2.md) | Microsoft Agent Framework — Foundry V1 vs V2 comparison |
| [architecture/architecture_diagram.html](architecture/architecture_diagram.html) | Interactive architecture diagrams (Demo & Production) with Azure icons |
