# Demo Flow — Zava Processing Inc. Ticket Processing System

> **Audience:** Stakeholders & engineering leadership  
> **Duration:** ~5 minutes (live walkthrough)  
> **Prerequisites:** Either the Azure deployment running, or backend (port 8000) and frontend dev server (port 5173) running locally

---

## Pre-Demo Checklist

### Option A — Use the deployed Azure environment

1. Open the **Static Web App** URL in your browser (the frontend will call the deployed backend automatically).
2. Verify the backend health endpoint returns `200 OK` at `<backend-url>/health`.

### Option B — Run locally

1. **Start the backend:**
   ```bash
   cd backend && uvicorn app.main:app --reload --port 8000
   ```
2. **Start the frontend:**
   ```bash
   cd frontend && npm run dev
   ```
3. Open **http://localhost:5173** in your browser.
4. Ensure the Cosmos DB Emulator is running (or `APP_ENV=development` for in-memory fallback).

---

## Scene-by-Scene Walkthrough

### Scene 1 — Ticket Ingestion (Tab 1)

**Goal:** Show how a Salesforce ticket arrival is simulated and ingested.

| Step | Action | What the audience sees |
|------|--------|----------------------|
| 1 | Click **"🎫 Ticket Ingestion"** tab | The ingestion form with sample ticket presets |
| 2 | Click one of the **"Quick Demo"** sample buttons (e.g., *#1 Happy Path*) | Form auto-populates with realistic ticket data **and the matching PDF auto-attaches** (shows filename + size) |
| 3 | Click **"Submit Ticket"** | Spinner → success toast with ticket ID; live Salesforce feed updates on the right; auto-navigates to Tab 2 |

**Talking points:**
- *"In production, this form would be replaced by the Salesforce Change Data Capture connector that automatically pushes new tickets into our pipeline."*
- *"Notice how clicking a sample button auto-fills the form AND attaches the matching PDF invoice — the PDF is fetched from the backend's static file server. In production, attachments would come from the Salesforce API."*
- *"The backend immediately persists the ticket to Cosmos DB and queues PDF extraction in the background."*

---

### Scene 2 — Extraction Results (Tab 2)

**Goal:** Show structured data extracted from the raw ticket and PDF attachment.

| Step | Action | What the audience sees |
|------|--------|----------------------|
| 1 | Click **"📋 Extraction Results"** tab | Select the ticket you just submitted |
| 2 | Wait ~3 seconds for polling to pick up the extraction result | Status badge changes from "Extracting…" to "Extracted" |
| 3 | Review the 4-panel layout: **Metadata**, **Financials**, **Line Items**, **Confidence** | Extracted invoice number, vendor, amounts, per-line details, OCR confidence scores |
| 4 | Click **"Trigger AI Processing →"** | Button sends the ticket to the next stage |

**Talking points:**
- *"Stage A uses PyMuPDF for basic metadata and Azure Content Understanding for structured table extraction from the PDF."*
- *"Confidence scores let downstream stages know how reliable the extracted data is — low confidence triggers manual review."*
- *"At scale, extraction runs in parallel across millions of tickets using Azure Functions with event-driven auto-scaling."*

---

### Scene 3 — AI Processing Results (Tab 3)

**Goal:** Show the Foundry V2 agent's standardization, summarization, and routing decision.

| Step | Action | What the audience sees |
|------|--------|----------------------|
| 1 | Click **"🤖 AI Processing"** tab | The ticket now shows "AI Processing…" status |
| 2 | Wait for agent completion (~5–15 seconds) | Status changes to "AI Processed"; results appear |
| 3 | Review **Standardized Codes** panel | Vendor code (e.g., VND-ABC-001), product codes, department mapping |
| 4 | Review **AI Summary** panel | 3–5 sentence executive summary of the ticket |
| 5 | Review **Next Action** badge | Routed action: "Route to Invoice Processing" or "Route to Manual Review" |
| 6 | Click **"Trigger Invoice Processing →"** (if action = invoice_processing) | Ticket moves to final stage |

**Talking points:**
- *"The Foundry V2 agent reads both structured data and the raw ticket text. It cross-references our code mapping database to standardize vendor and product codes."*
- *"The agent autonomously decides the next action based on configurable rules — for example, unapproved vendors are routed to manual review instead of automatic invoicing."*
- *"This is where AI Gateway (Azure API Management) manages the agent calls — providing rate limiting, token tracking, and observability at scale."*

---

### Scene 4 — Invoice Processing Results (Tab 4)

**Goal:** Show automated invoice validation and simulated payment submission.

| Step | Action | What the audience sees |
|------|--------|----------------------|
| 1 | Click **"💳 Invoice Processing"** tab | Results loading for the selected ticket |
| 2 | Review **Validation Results** | ✅/❌ for each check: invoice number, amount match, due date, vendor status |
| 3 | Review **Payment Submission** panel | Payment ID, amount, method, submission timestamp |
| 4 | Status badge shows **"Invoice Processed"** | Full pipeline complete |

**Talking points:**
- *"The invoice processing agent validates the invoice against extracted data and business rules."*
- *"In production, the payment submission would call the actual ERP/payment system API through the AI Gateway."*
- *"If validation fails (e.g., amount discrepancy or past-due invoice), the agent flags the issue and routes to manual review instead of submitting payment."*

---

### Scene 5 — Dashboard (Tab 5)

**Goal:** Show aggregate metrics and operational health.

| Step | Action | What the audience sees |
|------|--------|----------------------|
| 1 | Click **"📊 Dashboard"** tab | Metric cards + status distribution chart |
| 2 | Point out the key metrics | Total tickets, average processing time, success rate |
| 3 | Submit 2–3 more sample tickets quickly | Metrics update in real-time as pipeline completes |

**Talking points:**
- *"The dashboard queries Cosmos DB aggregate metrics in real time."*
- *"At 4 million tickets per week, these metrics would be backed by Cosmos DB change feed aggregations and Azure Monitor dashboards."*
- *"The success rate tracks end-to-end pipeline completion — including error recovery via the reprocess button."*

---

## Error Scenario (Optional)

To demonstrate error handling:

1. Go to **Tab 1** → Submit a ticket with a corrupted or non-invoice PDF.
2. Observe the extraction result shows an **Error** state.
3. Click **"Reprocess"** to retry.

**Talking point:** *"The system is designed for resilience — every stage persists its state to Cosmos DB, so we can retry from any failure point without losing work."*

---

## Key Architecture Highlights for Q&A

| Question | Answer |
|----------|--------|
| **How does this scale to 4M tickets/week?** | Azure Functions event-driven scaling, Cosmos DB auto-scale RUs, and Container Apps horizontal pod auto-scaling. |
| **What about latency?** | Cosmos DB provides single-digit ms reads; Content Understanding processes PDFs in ~2–5 seconds; agents complete in ~5–15 seconds. |
| **What if an agent fails?** | Each ticket tracks its status in Cosmos DB. Failed tickets are marked with `error` status and can be reprocessed. The UI provides a one-click reprocess button. |
| **How do you handle concurrent processing?** | Each ticket is an independent document in Cosmos DB. Partition key (`ticketId`) ensures no cross-partition contention. Azure Functions scale out horizontally. |
| **Why Cosmos DB over SQL?** | Flexible schema for structured + unstructured data, built-in vector search for future RAG patterns, automatic global distribution, and elastic scale from dev to 4M+ tickets/week. |

---

*End of demo flow.*
