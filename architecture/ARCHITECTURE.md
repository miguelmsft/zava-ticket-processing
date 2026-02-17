# Architecture — Zava Processing Inc. Ticket Processing System

## 1. Overview

This system automates ticket processing for **Zava Processing Inc.** using an AI-powered pipeline that extracts information from incoming support tickets (simulating Salesforce), processes them through AI agents, and performs automated invoice actions. It is designed as a **demo** reflecting production-scale architecture decisions capable of handling **4M+ tickets/week**.

---

## 2. Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Database** | Azure Cosmos DB for NoSQL (Serverless) | Schema-less JSON, Change Feed for event-driven pipeline, elastic scale, Foundry integration |
| **PDF Processing** | Azure Content Understanding + Python (PyMuPDF/pdfplumber) | Latest Microsoft recommendation, prebuilt invoice analyzer, async at scale |
| **AI Agents** | Foundry Agent Service V2 (New) — `azure-ai-projects` ≥ 2.0.0b3, Responses API | Direct SDK, managed agents with MCP/OpenAPI tools, versioned agents |
| **AI Agent Fallback** | Local simulation in backend Python (FastAPI) | Auto-fallback when Azure Functions return non-200; produces realistic demo data without AI model quota |
| **AI Models** | gpt-5-mini (agent reasoning), gpt-4.1 (agent reasoning), text-embedding-3-large (embeddings) | GlobalStandard SKU, deployed via Azure AI Services |
| **MCP Server** | Azure Functions with `mcpToolTrigger` binding | Native Azure Functions MCP extension for Cosmos DB operations |
| **AI Gateway** | Azure API Management BasicV2 *(optional — scaffolded but disabled for demo)* | Production path: centralized auth/rate-limiting/monitoring for agent tools |
| **Backend** | Python (FastAPI) on Azure Container Apps | Async microservices, auto-scaling, serverless containers |
| **Agent Functions** | Azure Functions (HTTP triggers) on shared B2 Linux App Service Plan | 5 function apps; HTTP triggers for demo (Change Feed triggers for production). Note: B2 plan reduces cold starts vs B1; backend auto-falls back to local simulation on 503 |
| **Frontend** | React + Vite + TypeScript + Tailwind CSS | Professional demo quality, 5-tab UI with glassmorphism, animated progress rings, real-time updates |
| **Frontend Hosting** | Azure Static Web Apps (Free) | Optimized for SPA, global CDN |
| **Infra-as-Code** | Bicep via Azure Developer CLI (`azd`) | 11 Bicep modules, `azd up` for one-command provision + deploy |
| **Container Registry** | Azure Container Registry (Basic) | Backend Docker image storage |
| **Authentication** | User-Assigned Managed Identity (`DefaultAzureCredential`) | Cosmos DB + Blob Storage auth without keys; AZURE_CLIENT_ID set by Bicep |

---

## 3. High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React + Vite)                         │
│                          Azure Static Web Apps                               │
│                                                                              │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌───────────┐ │
│  │ Tab 1:   │ │ Tab 2:       │ │ Tab 3:       │ │ Tab 4:   │ │ Tab 5:    │ │
│  │ Ticket   │ │ Extraction   │ │ AI Processing│ │ Invoice  │ │ Dashboard │ │
│  │ Ingest   │ │ Results      │ │ Results      │ │ Results  │ │ Overview  │ │
│  └────┬─────┘ └──────┬───────┘ └──────┬───────┘ └────┬─────┘ └─────┬─────┘ │
│       │               │               │              │              │       │
└───────┼───────────────┼───────────────┼──────────────┼──────────────┼───────┘
        │               │               │              │              │
        ▼               ▼               ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND API (FastAPI)                                │
│                      Azure Container Apps                                    │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ POST /tickets│  │ GET /tickets │  │ GET /tickets  │  │ GET /dashboard │  │
│  │ (ingest)     │  │ /{id}/extract│  │ /{id}/process │  │ /metrics       │  │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  └────────────────┘  │
│         │                                                                    │
└─────────┼────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     STAGE A: INGESTION & EXTRACTION                          │
│                                                                              │
│  ┌─────────────────────┐     ┌──────────────────────────────────┐           │
│  │ Step 1: PyMuPDF      │     │ Step 2: Invoice Data Extraction  │           │
│  │ (always runs)        │     │ (user selects method on Tab 1):  │           │
│  │ page count, size,    │     │                                  │           │
│  │ raw text, metadata   │     │  ● Python Regex (~40ms, default) │           │
│  └──────────┬──────────┘     │  ● Content Understanding (~30s)  │           │
│             │                 └──────────────┬───────────────────┘           │
│             │                                │                               │
│             └────────────┬───────────────────┘                               │
│                          ▼                                                   │
│              ┌───────────────────────┐                                       │
│              │  Persist to Cosmos DB │  ← status: "extracted"                │
│              │  (tickets container)  │                                       │
│              └───────────┬───────────┘                                       │
└──────────────────────────┼───────────────────────────────────────────────────┘
                           │
                           ▼ Backend HTTP call to Stage C Function
┌──────────────────────────────────────────────────────────────────────────────┐
│                     STAGE B: AI INFORMATION PROCESSING                       │
│                     (Azure Function — HTTP Trigger)                          │
│                     POST /api/process-ticket                                 │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐        │
│  │  Foundry Agent V2 (New) — "Information Processing Agent"        │        │
│  │  SDK: azure-ai-projects ≥ 2.0.0b3 | API: Responses API         │        │
│  │                                                                  │        │
│  │  Tools:                                                          │        │
│  │   • MCP Tool → Cosmos DB MCP Server (Azure Function, direct)    │        │
│  │   • OpenAPI Tool → Code Mapping API (Azure Function)             │        │
│  │                                                                  │        │
│  │  Actions:                                                        │        │
│  │   1. Read extracted ticket data from Cosmos DB                   │        │
│  │   2. Standardize numbers & codes (using code mapping reference)  │        │
│  │   3. Create summary highlighting key points                     │        │
│  │   4. Assign next action for the case                            │        │
│  │   5. Persist results back to Cosmos DB                          │        │
│  └──────────────────────────────────────────────────────────────────┘        │
│                                                                              │
│              ┌───────────────────────┐                                       │
│              │  Update Cosmos DB     │  ← status: "ai_processed"             │
│              │  (tickets container)  │                                       │
│              └───────────┬───────────┘                                       │
└──────────────────────────┼───────────────────────────────────────────────────┘
                           │
                           ▼ Backend HTTP call to Stage C Function
┌──────────────────────────────────────────────────────────────────────────────┐
│                     STAGE C: INVOICE PROCESSING                              │
│                     (Azure Function — HTTP Trigger)                          │
│                     POST /api/process-invoice                                │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐        │
│  │  Foundry Agent V2 (New) — "Invoice Processing Agent"            │        │
│  │  SDK: azure-ai-projects ≥ 2.0.0b3 | API: Responses API         │        │
│  │                                                                  │        │
│  │  Tools:                                                          │        │
│  │   • MCP Tool → Cosmos DB MCP Server (Azure Function, direct)    │        │
│  │   • OpenAPI Tool → Payment Processing API (Azure Function)       │        │
│  │                                                                  │        │
│  │  Actions:                                                        │        │
│  │   1. Read AI processing results from Cosmos DB                   │        │
│  │   2. Validate invoice number                                    │        │
│  │   3. Check if amount is correct                                 │        │
│  │   4. Verify due date                                            │        │
│  │   5. Submit invoice for payment (simulated API call)            │        │
│  │   6. Persist results back to Cosmos DB                          │        │
│  └──────────────────────────────────────────────────────────────────┘        │
│                                                                              │
│              ┌───────────────────────┐                                       │
│              │  Update Cosmos DB     │  ← status: "invoice_processed"        │
│              │  (tickets container)  │                                       │
│              └───────────┬───────────┘                                       │
└──────────────────────────┼───────────────────────────────────────────────────┘
                           │
                           ▼
                    Pipeline Complete
```

---

## 4. Component Details

### 4.1 Frontend — React + Vite + TypeScript

**Hosting:** Azure Static Web Apps

The UI provides 5 tabs, each connected to backend APIs via polling or WebSocket for real-time status updates.

| Tab | Component | Backend Endpoint | Description |
|-----|-----------|-----------------|-------------|
| **Tab 1** | `TicketIngestion` | `POST /api/tickets` | Form to submit ticket + PDF upload. Simulates Salesforce arrival. Extraction method toggle (Python Regex / Content Understanding). |
| **Tab 2** | `ExtractionResults` | `GET /api/tickets/{id}/extraction` | Displays extracted title, description, attachment metadata in structured format. Shows extraction method badge (⚡ Python Regex / 🧠 Content Understanding). |
| **Tab 3** | `AIProcessingResults` | `GET /api/tickets/{id}/ai-processing` | Shows standardized codes, summary, assigned next action. |
| **Tab 4** | `InvoiceProcessing` | `GET /api/tickets/{id}/invoice-processing` | Shows validation results, payment submission status, errors. |
| **Tab 5** | `Dashboard` | `GET /api/dashboard/metrics` | Metrics with animated progress rings, count-up numbers, success rate. |

**Real-time updates:** Frontend polls the backend every 2-3 seconds for status changes on in-progress tickets. Dashboard uses aggregated metrics from Cosmos DB.

**UI Polish (Phase 11):**
- Glassmorphism cards (`bg-white/80 backdrop-blur`) with colored left accents per stage (indigo/teal/violet/emerald)
- Tab fade-in/slide-up transitions with mesh gradient background
- SVG circular progress rings for success rate; `requestAnimationFrame`-based count-up for numbers
- Enhanced file upload dropzone with gradient dashed border
- Quick Demo buttons with PDF auto-attach (fetches sample PDF from backend automatically)

---

### 4.2 Backend API — FastAPI on Azure Container Apps

**Purpose:** REST API that serves as the bridge between the frontend and the processing pipeline.

**Key responsibilities:**
- Receive ticket submissions (with PDF uploads)
- Trigger Stage A (ingestion & extraction)
- Serve ticket data at each pipeline stage to the frontend
- Provide dashboard metrics

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/tickets` | Submit a new ticket with PDF attachment |
| `GET` | `/api/tickets` | List all tickets with current pipeline status |
| `GET` | `/api/tickets/{id}` | Get full ticket details (all stages) |
| `GET` | `/api/tickets/{id}/extraction` | Get extraction results for a ticket |
| `GET` | `/api/tickets/{id}/ai-processing` | Get AI processing results for a ticket |
| `POST` | `/api/tickets/{id}/process-ai` | Trigger Stage B (calls the Stage B Azure Function; falls back to local simulation on non-200) |
| `POST` | `/api/tickets/{id}/process-invoice` | Trigger Stage C (calls the Stage C Azure Function; falls back to local simulation on non-200) |
| `GET` | `/api/tickets/{id}/invoice-processing` | Get invoice processing results for a ticket |
| `POST` | `/api/tickets/{id}/reprocess` | Manually re-trigger processing for a ticket |
| `DELETE` | `/api/tickets/{id}` | Delete a ticket |
| `GET` | `/api/dashboard/metrics` | Aggregated metrics for the dashboard |

> **Implementation note:** Dashboard metrics are computed via Python aggregation (not SQL GROUP BY) because Cosmos DB Serverless does not support cross-partition GROUP BY queries. The backend fetches a lightweight projection of all tickets and aggregates in-memory.

---

### 4.3 Stage A: Ingestion & Extraction

**Runtime:** Runs inline in the FastAPI backend (triggered by `POST /api/tickets`).

**User-selectable extraction method:** The user chooses the extraction method via a toggle on Tab 1 before submitting a ticket. The `extraction_method` parameter (`"regex"` or `"cu"`) is sent with the form and controls which extraction path is used.

**Two-step extraction strategy:**

#### Step 1: Standard Python Extraction (always runs)
- **Library:** PyMuPDF (`fitz`)
- **Extracts:** PDF page count, file size, creation date, basic text content (first 2,000 chars)
- **Also from ticket form:** Title, description, tags, priority, submitter

#### Step 2: Invoice Data Extraction (user-selected method)

| Method | Speed | Implementation | Confidence Scores |
|--------|-------|----------------|-------------------|
| **Python Regex** (default) | ~40ms | `_extract_fallback()` — regex patterns on PyMuPDF text | Simulated (0.85–0.96) |
| **Content Understanding** | ~30s | `_extract_with_cu_sdk()` — Azure `prebuilt-invoice` analyzer via SAS URL | Real AI (0.78–0.88) |

Both methods extract the same fields: invoice number, vendor name/address, dates, PO number, subtotal, tax, total, payment terms, line items (description, product code, quantity, unit price, amount), and special flags.

**Line item amount fix:** When Content Understanding returns `0` for a line item amount, the system computes `amount = quantity × unitPrice` via `_fix_line_item_amounts()`.

**Output:** Combined extraction results stored in Cosmos DB with `status: "extracted"`. The `extractionMethod` field is persisted in the result so Tab 2 can display which method was used.

---

### 4.4 Stage B: AI Information Processing

**Runtime:** Azure Function with HTTP trigger (`POST /api/process-ticket`). Called by the FastAPI backend when the UI triggers processing. In production, this would use a Cosmos DB Change Feed trigger that fires automatically on `status == "extracted"`.

**Agent:** Foundry Agent V2 (New) — "Information Processing Agent"

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition, MCPTool, OpenApiTool,
    OpenApiFunctionDefinition, OpenApiAnonymousAuthDetails,
)

project_client = AIProjectClient(
    endpoint=AI_PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai_client = project_client.get_openai_client()

# MCP Tool: Cosmos DB access
mcp_tool = MCPTool(
    server_label="cosmos-db-tickets",
    server_url=MCP_COSMOS_ENDPOINT,  # Azure Function URL
    require_approval="never",
)

# OpenAPI Tool: Code Mapping API
openapi_tool = OpenApiTool(
    openapi=OpenApiFunctionDefinition(
        name="code_mapping_api",
        spec=spec,  # Loaded from openapi/code_mapping_api.yaml
        auth=OpenApiAnonymousAuthDetails(),
    ),
)

# Create versioned agent
agent = project_client.agents.create_version(
    agent_name="information-processing-agent",
    definition=PromptAgentDefinition(
        model=MODEL_DEPLOYMENT_NAME,
        instructions=AGENT_INSTRUCTIONS,
        tools=[mcp_tool, openapi_tool],
    ),
)

# Run via Responses API
response = openai_client.responses.create(
    input=user_input,
    extra_body={
        "agent": {
            "type": "agent_reference",
            "name": agent.name,
            "version": agent.version,
        },
    },
)
```

**Tools available:**
- **MCP Tool** → Cosmos DB MCP Server (read/write ticket data) — hosted on **Azure Functions** (direct, not via APIM)
- **OpenAPI Tool** → Code Mapping API (lookup reference codes) — hosted on **Azure Functions**

**Processing flow:**
1. Backend calls `POST /api/process-ticket` on the Stage B Function App
2. Function validates ticket status == "extracted", sets status to "ai_processing"
3. Creates Foundry Agent V2 with MCP + OpenAPI tools
4. Agent reads extracted data from Cosmos DB via `read_ticket` MCP tool
5. Agent looks up code mapping reference via OpenAPI tool
6. Agent standardizes numbers/codes, creates summary, assigns next action
7. Agent writes results back to Cosmos DB via `update_ticket` MCP tool → `status: "ai_processed"`
8. Function handles MCP approval flow (auto-approves for demo)

---

### 4.5 Stage C: Invoice Processing

**Runtime:** Azure Function with HTTP trigger (`POST /api/process-invoice`). Called by the FastAPI backend when the UI triggers invoice processing. In production, this would use a Cosmos DB Change Feed trigger that fires automatically on `status == "ai_processed"` with `nextAction == "invoice_processing"`.

**Agent:** Foundry Agent V2 (New) — "Invoice Processing Agent"

Uses the same pattern as Stage B:
- `AIProjectClient` → `project_client.agents.create_version()` → `openai_client.responses.create()` with `agent_reference`
- Agent name: `"invoice-processing-agent"`
- Agent logic separated in `invoice_agent_logic.py`

**Tools available:**
- **MCP Tool** → Cosmos DB MCP Server (read AI processing results) — hosted on **Azure Functions** (direct)
- **OpenAPI Tool** → Payment Processing API (simulated) — hosted on **Azure Functions**

**Processing flow:**
1. Backend calls `POST /api/process-invoice` on the Stage C Function App
2. Function validates ticket status == "ai_processed" and nextAction == "invoice_processing"
3. Creates Foundry Agent V2 with MCP + Payment API tools
4. Agent reads AI processing results from Cosmos DB via `read_ticket` MCP tool
5. Agent validates invoice (number, amount, due date, vendor approval, budget)
6. If valid → Agent calls Payment API via OpenAPI tool to submit payment
7. Agent writes results back to Cosmos DB via `update_ticket` MCP tool → `status: "invoice_processed"`
8. If nextAction ≠ "invoice_processing" (e.g., "manual_review") → Stage C is skipped; status set to "completed_manual_review"

---

### 4.6 MCP Server & API Functions

#### Cosmos DB MCP Server (Azure Function — `mcp-cosmos`)

Hosted as a **standalone Azure Function App** using the native `mcpToolTrigger` binding from the Azure Functions MCP extension. The Foundry Agent V2 agents call this MCP server **directly** (not via APIM in the current deployment).

**URL:** `https://<prefix>-func-mcp-cosmos.azurewebsites.net`

| MCP Tool | Description |
|----------|-------------|
| `read_ticket` | Point-read a single ticket by `ticketId` (partition key). Returns the full document. |
| `update_ticket` | Partial update via read-modify-write with deep merge. Accepts `ticket_id` + `updates_json`. |
| `query_tickets_by_status` | Cross-partition query filtered by pipeline status. Returns ticket summaries (max 50). |

#### Code Mapping API (Azure Function — `api-code-mapping`)

REST/OpenAPI API (not MCP). Called by agents via `OpenApiTool`. Reads reference data from the `code-mappings` Cosmos DB container.

| Endpoint | Description |
|----------|-------------|
| `GET /api/codes/{codeType}` | List all codes of a given type |
| `GET /api/codes/{codeType}/{code}` | Look up a specific code |
| `POST /api/codes/batch-lookup` | Batch lookup multiple codes |
| `GET /api/codes` | List all code types |

#### Payment Processing API (Azure Function — `api-payment`)

Simulated REST/OpenAPI API. Called by the Invoice Processing Agent via `OpenApiTool`.

| Endpoint | Description |
|----------|-------------|
| `POST /api/invoices/validate` | Validate an invoice (number, amount, due date) |
| `POST /api/invoices/submit-payment` | Submit an invoice for payment (simulated ACH) |
| `GET /api/invoices/{invoiceNumber}/status` | Check payment status |

#### Azure API Management — AI Gateway *(optional, disabled for demo)*

**SKU:** BasicV2 — Scaffolded in `infra/modules/apim.bicep` with `deployApim = false`.

When enabled (`deployApim = true`), APIM sits in front of the MCP server and API Functions, providing:
- Rate limiting (per-agent, per-tool)
- Authentication policies
- Request/response logging
- Application Insights analytics
- Token metering for AI calls

**Production recommendation:** Enable APIM at 4M+ tickets/week for centralized control and monitoring.

---

### 4.7 Azure Cosmos DB for NoSQL

**Database:** `zava-ticket-processing`

**Containers:**

| Container | Partition Key | Purpose |
|-----------|--------------|---------|
| `tickets` | `/ticketId` | Main ticket data across all pipeline stages |
| `code-mappings` | `/codeType` | Reference data for code standardization |
| `metrics` | `/date` | Aggregated processing metrics for dashboard |

#### Ticket Document Schema

```json
{
  "id": "uuid",
  "ticketId": "ZAVA-2026-00001",
  "status": "submitted | extracted | ai_processed | invoice_processed | error",
  "createdAt": "2026-02-06T10:00:00Z",
  "updatedAt": "2026-02-06T10:05:00Z",
  
  "ingestion": {
    "title": "Invoice Processing Request - Vendor ABC",
    "description": "Please process the attached invoice for payment...",
    "tags": ["invoice", "vendor-abc", "urgent"],
    "priority": "high",
    "submitter": "john.doe@zavaprocessing.com",
    "attachmentFilename": "invoice_vendor_abc_2026.pdf",
    "attachmentUrl": "https://storage.../invoice.pdf"
  },
  
  "extraction": {
    "completedAt": "2026-02-06T10:01:30Z",
    "processingTimeMs": 1500,
    "extractionMethod": "regex | cu",
    "basicMetadata": {
      "pageCount": 3,
      "fileSize": "245KB",
      "pdfCreationDate": "2026-01-15"
    },
    "contentUnderstanding": {
      "invoiceNumber": "INV-2026-78432",
      "vendorName": "ABC Industrial Supplies",
      "vendorAddress": "123 Industrial Way, Houston TX 77001",
      "invoiceDate": "2026-01-15",
      "dueDate": "2026-02-15",
      "subtotal": 12500.00,
      "tax": 1031.25,
      "totalAmount": 13531.25,
      "currency": "USD",
      "lineItems": [
        {
          "description": "Industrial Grade Valve Assembly (Model V-4200)",
          "quantity": 50,
          "unitPrice": 150.00,
          "amount": 7500.00,
          "productCode": "VLV-4200-IND"
        },
        {
          "description": "High-Pressure Seal Kit (Compatible V-4200)",
          "quantity": 100,
          "unitPrice": 50.00,
          "amount": 5000.00,
          "productCode": "SK-HP-4200"
        }
      ],
      "confidenceScores": {
        "invoiceNumber": 0.98,
        "totalAmount": 0.99,
        "vendorName": 0.97
      }
    }
  },
  
  "aiProcessing": {
    "completedAt": "2026-02-06T10:02:45Z",
    "processingTimeMs": 3200,
    "agentName": "information-processing-agent",
    "agentVersion": "1",
    "standardizedCodes": {
      "vendorCode": "ABCIND-001",
      "productCodes": ["VLV-4200-IND-STD", "SK-HP-4200-STD"],
      "departmentCode": "PROC-MFG-001",
      "costCenter": "CC-4500"
    },
    "summary": "Invoice from ABC Industrial Supplies for 50 valve assemblies and 100 seal kits totaling $13,531.25 USD. Items are standard procurement for manufacturing line. Vendor is approved. All product codes validated against catalog. Due date is February 15, 2026 — within 30-day payment terms.",
    "nextAction": "invoice_processing",
    "confidence": 0.95
  },
  
  "invoiceProcessing": {
    "completedAt": "2026-02-06T10:04:00Z",
    "processingTimeMs": 2800,
    "agentName": "invoice-processing-agent",
    "agentVersion": "1",
    "validations": {
      "invoiceNumberValid": true,
      "amountCorrect": true,
      "dueDateValid": true,
      "vendorApproved": true,
      "budgetAvailable": true
    },
    "paymentSubmission": {
      "submitted": true,
      "paymentId": "PAY-2026-99201",
      "submittedAt": "2026-02-06T10:03:55Z",
      "expectedPaymentDate": "2026-02-14",
      "paymentMethod": "ACH Transfer"
    },
    "errors": []
  }
}
```

---

## 5. Data Flow Summary

```
User submits ticket via UI (Tab 1)
        │
        ▼
   ┌─────────┐     ┌──────────────────┐     ┌──────────────────────────┐
   │ FastAPI  │────▶│ Python Extraction │────▶│ Content Understanding    │
   │ Backend  │     │ (basic fields)   │     │ (PDF → structured data) │
   └─────────┘     └──────────────────┘     └──────────────────────────┘
        │                                              │
        ▼                                              │
   Cosmos DB ◀─────────────────────────────────────────┘
   status: "extracted"
        │
        ▼ (UI triggers via Backend → HTTP POST to Stage B Function)
   Azure Function → Foundry Agent V2 ("Information Processing")
        │               │── MCP Tool → Cosmos DB MCP Server (Azure Function)
        │               │── OpenAPI Tool → Code Mapping API (Azure Function)
        │               └── Standardize, Summarize, Assign Action
        ▼
   Cosmos DB
   status: "ai_processed"
        │
        ▼ (UI triggers via Backend → HTTP POST to Stage C Function)
   Azure Function → Foundry Agent V2 ("Invoice Processing")
        │               │── MCP Tool → Cosmos DB MCP Server (Azure Function)
        │               │── OpenAPI Tool → Payment API (Azure Function)
        │               └── Validate, Submit Payment
        ▼
   Cosmos DB
   status: "invoice_processed"
        │
        ▼
   Frontend displays results (Tabs 2-5)

   Production variant: Change Feed triggers replace HTTP calls,
   enabling fully event-driven pipeline automation.
```

---

## 6. Scale Considerations

Although this is a demo with low data volume, the architecture is designed for **4M+ tickets/week in production**:

| Concern | Design Decision |
|---------|----------------|
| **Throughput** | Cosmos DB Serverless handles burst (auto-scales RUs); Container Apps auto-scale replicas |
| **Concurrency** | FastAPI async handlers; Content Understanding async operations; Azure Functions concurrent executions |
| **Partitioning** | Cosmos DB partitioned by `ticketId` (high cardinality); HPK option with `tenantId/ticketId` for multi-tenant |
| **Event-driven** | Demo uses HTTP triggers for UI-controlled timing; production uses Change Feed for fully decoupled, auto-scaling stages |
| **PDF Processing** | Content Understanding handles concurrent requests; Python extraction is stateless and parallelizable |
| **Agent Calls** | Foundry Agent Service is managed; MCP server on Azure Functions scales independently; APIM (when enabled) adds rate limiting |
| **Monitoring** | Application Insights across all components; Cosmos DB metrics; Azure Function diagnostics |
| **Function Hosting** | Shared B2 Linux App Service Plan for demo; production would use Elastic Premium (EP1+) for auto-scale |

---

## 7. Security Model (Production Reference)

| Layer | Mechanism |
|-------|-----------|
| **Authentication** | Microsoft Entra ID (Managed Identity between services) |
| **API Access** | APIM subscription keys + OAuth for MCP/OpenAPI tools |
| **Data Encryption** | Cosmos DB encryption at rest + TLS in transit |
| **Network** | VNet integration for Container Apps; Private endpoints for Cosmos DB |
| **Agent Trust** | Foundry content filters; RBAC on agent operations |

For the demo, we'll use simplified auth (API keys + DefaultAzureCredential).

> **Note (Phase 16 finding):** The Cosmos DB and Storage accounts must have `publicNetworkAccess: Enabled` since the Container App connects over the public internet (no VNet/private endpoint configured). This is set explicitly in the Bicep templates (`cosmos.bicep`, `storage.bicep`) to prevent regression.

---

## 8. Cloud Deployment & Testing Summary

Phase 16 performed comprehensive cloud end-to-end testing (API tests + Playwright UI tests) and discovered **13 bugs**, all fixed. Phases 17–21 discovered and fixed 4 additional bugs (stale error messages, 429 rate limiting, WEBSITE_RUN_FROM_PACKAGE conflict, function key regeneration on redeploy). Phase 22 ran full Playwright + backend E2E tests with 1 low-severity bug found (CU line item amounts return $0.00). Phase 23 enabled real Azure Content Understanding with Managed Identity auth (6 issues fixed). Phase 24 added a user-selectable extraction method toggle and fixed the CU line item amount bug. See PLAN.md for full details.

| # | Bug | Category | Resolution |
|---|-----|----------|------------|
| 1 | Cosmos DB env var mismatch | Config | `AliasChoices` accepts both Bicep and legacy naming |
| 2 | AI Processing URL missing API path | Config | Auto-append `/api/process-ticket` if missing |
| 3 | Blob Storage not connected (MI vs connection string) | Auth | Support `DefaultAzureCredential` when endpoint is set |
| 4 | Cosmos DB `publicNetworkAccess: Disabled` | Infra | Bicep + manual `az cosmosdb update` |
| 5 | Storage `publicNetworkAccess: Disabled` | Infra | Bicep + manual `az storage account update` |
| 6 | Blob container "invoices" missing | Infra | Bicep + manual `az storage container create` |
| 7 | All 5 Azure Functions return 503 | Runtime | Backend auto-falls back to local simulation on non-200 |
| 8 | Dashboard cross-partition GROUP BY | Query | Rewrote to Python-based aggregation |
| 9 | Dashboard formatMs shows raw floats | UI | `Math.round(ms * 10) / 10` |
| 10 | Ticket dropdown stale status | UI | Increment `refreshTrigger` on processing |
| 11 | "Processed Today" hardcoded to 0 | Backend | Compare `createdAt` with today's UTC date |
| 12 | Sample PDFs 404 in production | Docker | Dual-path resolution + COPY in Dockerfile |
| 13 | Cosmos query `c.created_at` vs `c.createdAt` | Query | Fixed field name to match document schema |

**Key architectural decisions validated:**
- Managed Identity auth works for Cosmos DB and Blob Storage from Container Apps
- Serverless Cosmos DB does NOT support cross-partition GROUP BY — must aggregate in application layer
- B1 Function Plan cold starts are too slow for reliable agent calls — simulation fallback is essential for demo
- `publicNetworkAccess` must be explicitly set in Bicep to avoid deployment surprises

See [PLAN.md — Phase 16](PLAN.md) for the full bug-by-bug resolution narrative.

---

## 9. Repository Structure

```
zava-ticket-processing/
├── .github/
│   └── copilot-instructions.md         ← Project instructions for Copilot
├── PLAN.md                              ← Implementation plan (24 phases)
├── README.md                            ← Project overview & getting started
├── azure.yaml                           ← Azure Developer CLI service manifest
│
├── architecture/                        ← Architecture documents & diagrams
│   ├── ARCHITECTURE.md                  ← This file
│   ├── architecture_diagram.html        ← Interactive Demo & Production diagrams
│   └── icons/                           ← Azure service icons (SVG + PNG)
│
├── backend/                             ← FastAPI backend (Azure Container Apps)
│   ├── app/
│   │   ├── main.py                      ← FastAPI app entry + CORS + static files
│   │   ├── config.py                    ← Settings & environment variables
│   │   ├── routers/
│   │   │   ├── tickets.py               ← Ticket CRUD + pipeline trigger endpoints
│   │   │   └── dashboard.py             ← Dashboard metrics aggregation
│   │   ├── services/
│   │   │   ├── extraction.py            ← Stage A: Python + Content Understanding
│   │   │   ├── ai_processing.py         ← Stage B orchestration (calls Function)
│   │   │   ├── invoice_processing.py    ← Stage C orchestration (calls Function)
│   │   │   ├── cosmos_client.py         ← Cosmos DB client singleton
│   │   │   ├── blob_storage.py          ← Azure Blob Storage for PDFs
│   │   │   ├── memory_store.py          ← In-memory store for local dev
│   │   │   └── storage.py               ← Storage abstraction layer
│   │   └── models/
│   │       └── ticket.py                ← Pydantic models (all pipeline stages)
│   ├── tests/                           ← 139 backend unit tests
│   ├── requirements.txt
│   └── Dockerfile
│
├── functions/                           ← Azure Functions (5 function apps)
│   ├── stage_b_ai_processing/           ← Foundry Agent V2 — Information Processing
│   │   ├── function_app.py              ← HTTP trigger + agent creation/execution
│   │   ├── agent_logic.py               ← Agent instructions, parsing, formatting
│   │   ├── requirements.txt
│   │   └── host.json
│   ├── stage_c_invoice_processing/      ← Foundry Agent V2 — Invoice Processing
│   │   ├── function_app.py              ← HTTP trigger + agent creation/execution
│   │   ├── invoice_agent_logic.py       ← Agent instructions, parsing, formatting
│   │   ├── requirements.txt
│   │   └── host.json
│   ├── mcp_cosmos/                      ← MCP Server for Cosmos DB (mcpToolTrigger)
│   │   ├── function_app.py              ← 3 MCP tools: read/update/query
│   │   ├── cosmos_helpers.py            ← Tool properties, context parsing, utilities
│   │   ├── requirements.txt
│   │   └── host.json
│   ├── api_code_mapping/                ← Code Mapping REST API (OpenAPI)
│   │   └── function_app.py              ← CRUD + batch lookup for reference codes
│   ├── api_payment/                     ← Payment Processing REST API (simulated)
│   │   ├── function_app.py              ← Validate, submit, check payment status
│   │   └── payment_logic.py             ← Payment validation business logic
│   ├── openapi/                         ← OpenAPI specs for agent tools
│   │   ├── code_mapping_api.yaml        ← Code Mapping API spec
│   │   └── payment_api.yaml             ← Payment API spec
│   └── tests/                           ← 127 function unit tests
│       ├── test_functions.py            ← MCP protocol + code mapping tests
│       ├── test_stage_b.py              ← Stage B agent logic tests
│       └── test_stage_c.py              ← Stage C agent logic tests
│
├── frontend/                            ← React + Vite + TypeScript + Tailwind
│   ├── src/
│   │   ├── App.tsx                      ← Root component with tab navigation
│   │   ├── main.tsx                     ← Entry point
│   │   ├── index.css                    ← Global styles (mesh gradient, animations)
│   │   ├── components/
│   │   │   ├── tabs/                    ← 5 tab components
│   │   │   │   ├── TicketIngestion.tsx   ← Tab 1: Submit ticket + auto-attach PDF
│   │   │   │   ├── ExtractionResults.tsx ← Tab 2: Extraction output display
│   │   │   │   ├── AIProcessingResults.tsx ← Tab 3: AI processing output
│   │   │   │   ├── InvoiceProcessing.tsx ← Tab 4: Invoice validation results
│   │   │   │   └── Dashboard.tsx        ← Tab 5: Metrics + progress rings
│   │   │   ├── ui/                      ← Reusable UI primitives
│   │   │   │   ├── Card.tsx             ← Glassmorphism card with accent colors
│   │   │   │   ├── Badge.tsx            ← Status badges
│   │   │   │   ├── Spinner.tsx          ← Loading spinner
│   │   │   │   └── ErrorRecovery.tsx    ← Error boundary component
│   │   │   └── layout/                  ← Layout components
│   │   │       ├── Header.tsx           ← Animated gradient header
│   │   │       └── TabNav.tsx           ← Tab navigation bar
│   │   ├── hooks/                       ← Custom React hooks
│   │   ├── services/                    ← API client
│   │   ├── types/                       ← TypeScript type definitions
│   │   ├── data/                        ← Sample data for Quick Demo
│   │   └── lib/                         ← Utility functions
│   ├── __tests__/                       ← 55 frontend unit tests
│   ├── tailwind.config.js               ← Custom animations, shadows, keyframes
│   ├── vite.config.ts
│   └── package.json
│
├── data/                                ← Sample data & PDF generation
│   ├── generate_sample_pdf.py           ← Script to create demo PDFs
│   ├── sample_tickets.json              ← 6 sample ticket presets
│   ├── code_mappings.json               ← Code mapping reference data
│   ├── seed_cosmos.py                   ← Script to seed Cosmos DB
│   └── sample_pdfs/                     ← Generated sample PDFs (6 files)
│
├── scripts/                             ← Deployment & operational scripts
│   ├── acr_deploy.ps1                   ← ACR container image deployment
│   ├── postdeploy.py                    ← Post-deployment setup (Cosmos seed, config)
│   ├── deploy.ps1                       ← Windows deployment helper
│   └── deploy.sh                        ← Linux deployment helper
│
├── docs/                                ← Documentation
│   ├── DEMO_FLOW.md                     ← Step-by-step demo script
│   └── MAF_Foundry_V1_vs_V2.md          ← Foundry V1 vs V2 comparison research
│
└── infra/                               ← Infrastructure as Code (Bicep + azd)
    ├── main.bicep                       ← Orchestrator (subscription scope)
    └── modules/
        ├── ai-services.bicep            ← Azure AI Services + model deployments
        ├── apim.bicep                   ← API Management BasicV2 (optional)
        ├── app-service-plan.bicep        ← Shared B2 Linux plan for functions
        ├── container-apps.bicep          ← Container Apps env + backend app
        ├── container-registry.bicep      ← ACR Basic for Docker images
        ├── cosmos.bicep                  ← Cosmos DB Serverless + 3 containers
        ├── function-app.bicep            ← Reusable function app module
        ├── managed-identity.bicep        ← User-assigned managed identity
        ├── monitoring.bicep              ← Log Analytics + Application Insights
        ├── static-web-app.bicep          ← Static Web App (Free)
        └── storage.bicep                 ← Storage account + blob containers
```

---

*Last Updated: February 16, 2026*
