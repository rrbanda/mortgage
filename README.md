# Small Business Loan Agent

A multi-agent system built with the [Google Agent Development Kit (ADK)](https://adk.dev/) that automates small business loan processing at **Cymbal Bank**. It demonstrates sequential multi-agent orchestration, human-in-the-loop approval, LLM-as-Judge validation, RAG-backed eligibility rules, and SQLite-backed repair & resume.

Runs locally against a Gemini API key, or fully deployed on Red Hat OpenShift AI via the AgentSandbox operator with OpenShell network enforcement.

## A. Overview

### Agent Details

| Property             | Value                                       |
| -------------------- | ------------------------------------------- |
| **Interaction Type** | Workflow                                    |
| **Complexity**       | Advanced                                    |
| **Agent Type**       | Multi-Agent (1 orchestrator + 4 sub-agents) |
| **Vertical**         | Financial Services                          |
| **Framework**        | Google ADK                                  |
| **Model**            | Gemini 2.5 Flash (configurable via `MODEL_NAME`) |

### Key Features

| Feature | Description |
|---|---|
| **Multi-Agent Orchestration** | Orchestrator coordinates 4 specialized sub-agents via `AgentTool` in a sequential workflow |
| **Multimodal Document Extraction** | Gemini reads loan application text/PDFs natively |
| **Structured Output** | Each sub-agent returns validated Pydantic models via `output_schema` / `output_key` |
| **Human-in-the-Loop (HITL)** | Orchestrator pauses after pricing to present results and wait for explicit user approval |
| **LLM-as-Judge Gate** | After-agent callback validates trajectory correctness and data grounding before showing responses |
| **RAG Eligibility Rules** | Underwriting agent retrieves live policy rules from AutoRAG vector store (falls back to static JSON locally) |
| **Repair & Resume** | SQLite workflow management tracks each step; workflow can pause on errors and resume from checkpoint |
| **Zero Cloud Dependencies** | State persisted to a local SQLite file — no Firestore, no GCP required for basic usage |

### Agent Flow

```
SmallBusinessLoanOrchestratorAgent
  ├── check_process_status          (SQLite state tool)
  ├── AgentTool(DocumentExtractionAgent)  →  LoanApplicationData
  ├── AgentTool(UnderwritingAgent)         →  UnderwritingReport
  ├── AgentTool(PricingAgent)              →  PricingResult
  └── AgentTool(LoanDecisionAgent)         →  LoanDecisionResult
```

---

## B. Demo Prompts

All prompts use fictional business names and people. Loan request IDs follow the format `SBL-YYYY-NNNNN`.

### Scenario 1 — Complete Application (Happy Path)

Paste in one message. The agent extracts all fields, underwrites, prices, then asks for approval.

```
Process loan application SBL-2025-00201.

Business: Sunrise Bakehouse LLC
Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201
Industry: Retail bakery, 5 years in business, 14 employees
Financials: $980K annual revenue, $62K net profit, no existing debt
Loan: $180,000 for 60 months to purchase a commercial deck oven and expand production line
Collateral: Existing baking equipment, estimated value $140,000
```

Expected flow: `check_process_status` → `DocumentExtractionAgent` → `UnderwritingAgent` → `PricingAgent` → approval prompt.

Reply **yes** to trigger `LoanDecisionAgent` and generate the decision letter.

---

### Scenario 2 — High-Revenue, Low-Risk Approval

```
Process loan application SBL-2025-00202.

Business: Blue Ridge Logistics Inc
Owner: Casey Hartman, casey@blueridgelogistics.com, 555-0202
Industry: Freight logistics, 9 years in business, 38 employees
Financials: $4.1M annual revenue, $310K net profit, $120K existing debt (equipment lease)
Loan: $500,000 for 84 months to purchase two refrigerated delivery trucks
Collateral: Fleet vehicles and warehouse equipment, estimated value $680,000
```

Expected: Tier 1 Low Risk, eligible, interest rate ~6-7%, approval prompt.

---

### Scenario 3 — Elevated Risk (Newer Business)

```
Process loan application SBL-2025-00203.

Business: Pixel & Grain Photography Studio
Owner: Alex Navarro, alex@pixelandgrain.com, 555-0203
Industry: Commercial photography, 2 years in business, 3 employees
Financials: $210K annual revenue, $18K net profit, no existing debt
Loan: $75,000 for 48 months to purchase camera systems and studio lighting
Collateral: Camera and studio equipment, estimated value $55,000
```

Expected: Tier 3 Elevated Risk (short operating history, loan-to-revenue ratio), higher interest rate, REVIEW status. Still reaches approval prompt — reply **yes** or **no** to complete.

---

### Scenario 4 — Missing Fields (Repair & Resume Flow)

```
Process loan application SBL-2025-00204.

Business: Mesa Verde Landscaping
Financials: $620K revenue, requesting $120K for 36 months
```

Expected: Agent extracts partial data, `UnderwritingAgent` halts because required fields are missing (owner name, contact, industry details). The error message lists exactly which fields are missing.

**To resume after adding the missing data:**

```
Resume SBL-2025-00204. Owner is Taylor Brooks, taylor@mesaverdeland.com, 555-0204.
Industry: landscaping and grounds maintenance, 6 years in business, 11 employees.
Net profit $48K, no existing debt. Collateral: landscaping equipment $90K.
```

---

### Scenario 5 — Status Check

After any application has been submitted, check its status in a new session:

```
What is the status of loan application SBL-2025-00201?
```

---

### Scenario 6 — Rejection (Ineligible)

```
Process loan application SBL-2025-00205.

Business: Coastal Events Pop-Up LLC
Owner: Riley Chen, riley@coastalevents.com, 555-0205
Industry: Event planning, 8 months in business, 2 employees
Financials: $85K annual revenue, $3K net profit, $40K existing business credit card debt
Loan: $250,000 for 60 months for venue deposits and equipment rental fleet
Collateral: None offered
```

Expected: Ineligible — operating history too short, loan-to-revenue ratio exceeds policy limit, insufficient collateral. Agent generates a decline decision letter.

---

## C. Running Locally

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A Gemini API key — get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Installation

```bash
git clone https://github.com/rrbanda/mortgage.git
cd mortgage

uv sync

cp .env.example .env
# Edit .env — set GOOGLE_API_KEY (or MAAS_API_KEY for Red Hat MaaS)
```

### Running with ADK Web UI

```bash
uv run adk web
```

Open `http://localhost:8000`, select `small_business_loan_agent`, and paste any prompt from Section B.

### Running as API Server

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8080
```

```bash
# Health check
curl http://localhost:8080/health

# Submit a loan application
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Process loan application SBL-2025-00201. Business: Sunrise Bakehouse LLC. Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201. Industry: retail bakery, 5 years, 14 employees. Financials: $980K revenue, $62K net profit, no debt. Loan: $180K for 60 months for oven purchase. Collateral: baking equipment $140K."
    }],
    "model": "loan-agent"
  }'

# Approve using the session_id from the previous response
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "yes"}],
    "model": "loan-agent",
    "session_id": "<session_id from previous response>"
  }'
```

---

## D. Deployed on RHOAI (AgentSandbox + OpenShell)

The agent is deployed on Red Hat OpenShift AI as an `agents.x-k8s.io/v1beta1 Sandbox` resource with OpenShell network enforcement. All infrastructure is GitOps-managed — no manual `oc apply` required.

### Repos

| Repo | Contents |
|---|---|
| `rrbanda/mortgage` | Agent source code, `Containerfile`, `server.py` |
| `rrbanda/ai-demos` | Kubernetes manifests — `agents/loan-agent/` |
| `rrbanda/ai-platforms` | ArgoCD Applications, AppProjects, AutoRAG |

### Architecture on Cluster

```
AgentHive (Open WebUI)
  └── /v1/chat/completions  ──►  loan-agent Pod (AgentSandbox)
                                   ├── OpenShell supervisor (network enforcement)
                                   ├── MaaS → Gemini 2.5 Flash
                                   ├── AutoRAG (OGX) → eligibility rules RAG
                                   └── SQLite state → PVC
```

### AutoRAG: Live Eligibility Rule Retrieval

The UnderwritingAgent retrieves loan eligibility policy from a live vector store rather than a static file. This makes the demo illustrate **Retrieval-Augmented Generation (RAG) in a production AI workflow** — the model only sees the rules most relevant to each specific application.

**Why AutoRAG instead of a static file?**

A static `eligibility_rules.json` works fine locally, but it has two weaknesses: the entire rule set is injected into every prompt (wasting context), and policy updates require a new code deployment. With AutoRAG the agent queries only the rules that match the current application's profile (revenue, operating history, loan-to-revenue ratio, industry), and policy updates are a re-seed operation with no code change.

**How it works — the retrieval chain:**

```
UnderwritingAgent (LLM)
  └── calls retrieve_eligibility_rules(query)
        └── POST /v1/vector_stores/{vs_id}/search   ← OGX AutoRAG API
              └── Milvus vector store
                    └── chunked & embedded eligibility_rules.json
```

1. Before running the eligibility check, the UnderwritingAgent LLM calls the `retrieve_eligibility_rules` tool with a query built from key application facts (e.g. "loan to revenue ratio 294%, 8 months operating history, no collateral").
2. The tool POSTs to the OGX AutoRAG search endpoint; OGX embeds the query and returns the top-5 most relevant policy chunks.
3. The returned text (plain English rule descriptions) is added to the underwriting context alongside the extracted application data.
4. The LLM evaluates the application against the retrieved rules and returns a structured `UnderwritingReport`.

**What's in the vector store?**

The vector store is seeded once from `sub_agents/underwriting/eligibility_rules.json`, which contains five core lending policy rules: minimum operating history, max loan-to-revenue ratio, revenue-band thresholds, high-risk industry flagging, and data consistency checks. Each rule is converted to a readable markdown section by `tools/seed_autorag.py` before embedding — raw JSON embeds poorly because the numbers lack semantic context.

Example of one embedded chunk (rule\_004):

```
## rule_004: Reject if loan-to-revenue ratio exceeds 75%
**Decision**: REJECT

**Conditions**:
- min loan to revenue ratio: 75%
```

For the Scenario 6 application (Coastal Events, 8 months operating, 294% LTR), the query `"8 months operating history, loan-to-revenue ratio 294%, no collateral, event planning"` retrieves rule\_003 and rule\_004 as the top hits — exactly the rules that produce the INELIGIBLE decision. The model only sees the two relevant rules, not the full rule set.

**Verified working on the demo cluster:**

The seed script was run against the OGX instance in the `autorag` namespace. Smoke-test output (cluster URL and IDs omitted):

```
Connecting to OGX …
  OGX status: ok
  Converted 5 eligibility rules to markdown (1 247 chars)
Uploading eligibility rules file …
  file_id: file-…
Creating vector store …
  vector_store_id: vs_…
Adding file to vector store (embedding …) …
  ingestion status: in_progress (attempt 1)
  ingestion status: completed (attempt 3)

Smoke-testing retrieval …
  'annual revenue loan to revenue ratio approval' → 2 hit(s)
    score=0.812  '## rule_001: Approve if annual revenue exceeds $500K and bu'
    score=0.774  '## rule_004: Reject if loan-to-revenue ratio exceeds 75%'
  'high risk industry cannabis gambling' → 2 hit(s)
    score=0.891  '## rule_005: Review if industry is in high-risk category'
    score=0.743  '## rule_002: Review if revenue is between $200K-$500K with 2'
  'years in business minimum requirement' → 2 hit(s)
    score=0.867  '## rule_003: Reject if business has less than 1 year of oper'
    score=0.821  '## rule_001: Approve if annual revenue exceeds $500K and bu'

✅  Done. Add to your config:
    AUTORAG_VECTOR_STORE_ID=vs_…
```

The embedding model is `nomic-embed-text-v1.5` (served by OGX from Milvus).

**Local fallback (no AutoRAG required):**

When `AUTORAG_BASE_URL` is not set (local dev with `GOOGLE_API_KEY`), the agent loads the full `eligibility_rules.json` into session state instead. The underwriting prompt adapts automatically — no code change needed to switch modes. `config.using_autorag()` returns `True` only when both `AUTORAG_BASE_URL` and `AUTORAG_VECTOR_STORE_ID` are set.

**Re-seeding after policy changes:**

```bash
# Run from mortgage/ after updating eligibility_rules.json
AUTORAG_BASE_URL=<your-cluster-autorag-url> \
  uv run python3 tools/seed_autorag.py
# Copy the printed vector_store_id into the loan-agent ConfigMap and redeploy.
```

---

### Secrets (all SealedSecrets — no plaintext in git)

| Secret | Contents |
|---|---|
| `loan-agent-auth` | MaaS API key (`llm-api-key`) |
| `openshell-client-tls` | OpenShell gateway TLS (`ca.crt`, `tls.crt`, `tls.key`) |

### Testing via AgentHive

1. Open `https://agenthive.<your-cluster-domain>`
2. Select **loan-agent** in the model dropdown
3. Paste any prompt from Section B

### Testing via API

```bash
# Against the cluster Route
BASE=https://loan-agent-loan-agent.<your-cluster-domain>

curl $BASE/health

curl -X POST $BASE/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Process loan application SBL-2025-00201. Business: Sunrise Bakehouse LLC. Owner: Morgan Ellis, 555-0201. Retail bakery, 5 years, $980K revenue, $62K profit. Requesting $180K for 60 months. Collateral: baking equipment $140K."
    }],
    "model": "loan-agent"
  }'
```

### Building and Pushing a New Image

```bash
cd mortgage

podman build --platform linux/amd64 -t small-business-loan-agent:latest -f Containerfile .

# Re-tag before every push (required — tag must match the new build)
REGISTRY=<your-openshift-registry-route>
podman tag small-business-loan-agent:latest $REGISTRY/loan-agent/small-business-loan-agent:latest
podman push $REGISTRY/loan-agent/small-business-loan-agent:latest
```

Then delete the running pod — `imagePullPolicy: Always` pulls the new image on restart.

---

## E. Configuration

### Local

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | — | Gemini API key (local dev) |
| `MODEL_NAME` | `gemini-2.5-flash` | Model for all agents |
| `STATE_DB_PATH` | `./mortgage_agent_state.db` | SQLite state file |

### RHOAI Cluster (set in `sandbox.yaml`)

| Variable | Value | Description |
|---|---|---|
| `MAAS_BASE_URL` | cluster URL | Red Hat MaaS endpoint |
| `MAAS_API_KEY` | from SealedSecret | MaaS API key |
| `MODEL_NAME` | `gemini-2.5-flash` | Model backend |
| `AUTORAG_BASE_URL` | cluster URL | OGX AutoRAG endpoint |
| `AUTORAG_VECTOR_STORE_ID` | `vs_...` | Seeded eligibility rules store |
| `STATE_DB_PATH` | `/app/data/state.db` | SQLite on PVC |
| `AGENT_NAME` | `loan-agent` | Model ID shown in Open WebUI |
| `BANK_NAME` | `Cymbal Bank` | Bank name in agent prompts |

---

## F. Customization

- **Prompts:** Each sub-agent has a `prompt.py`. Modify to change agent behavior or bank name references.
- **Eligibility rules:** Edit `sub_agents/underwriting/eligibility_rules.json` (or re-seed AutoRAG after changes).
- **Mock data:** Replace `MOCK_INTERNAL_RECORDS` in `sub_agents/underwriting/tools.py` with real CRM/API calls.
- **Pricing:** Replace `_determine_risk_tier` in `sub_agents/pricing/tools.py` with your pricing engine.

---

## G. Tests

```bash
uv sync --group dev
uv run pytest tests/unit
```

---

## License

Copyright 2026 Google LLC. Licensed under the Apache License, Version 2.0.
