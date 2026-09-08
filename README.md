# Small Business Loan Agent

A multi-agent system built with the [Google Agent Development Kit (ADK)](https://adk.dev/) that automates small business loan processing at **Cymbal Bank**. It demonstrates sequential multi-agent orchestration, human-in-the-loop approval, LLM-as-Judge validation, RAG-backed regulatory knowledge, ADK Agent Skills, and SQLite-backed repair & resume.

Runs locally against a Gemini API key, or fully deployed on Red Hat OpenShift AI via the AgentSandbox operator with OpenShell network enforcement.

## A. Overview

### Agent Details

| Property             | Value                                       |
| -------------------- | ------------------------------------------- |
| **Interaction Type** | Workflow                                    |
| **Complexity**       | Advanced                                    |
| **Agent Type**       | Multi-Agent (1 orchestrator + 4 sub-agents) |
| **Vertical**         | Financial Services                          |
| **Framework**        | Google ADK 2.8.0                            |
| **Model**            | Gemini 2.5 Flash (configurable via `MODEL_NAME`) |

### Key Features

| Feature | Description |
|---|---|
| **Multi-Agent Orchestration** | Orchestrator coordinates 4 specialized sub-agents via `AgentTool` in a sequential workflow |
| **Multimodal Document Extraction** | Gemini reads loan application text/PDFs natively |
| **Structured Output** | Each sub-agent returns validated Pydantic models via `output_schema` / `output_key` |
| **Human-in-the-Loop (HITL)** | Orchestrator pauses after pricing to present results and wait for explicit user approval |
| **LLM-as-Judge Gate** | After-agent callback validates trajectory correctness and data grounding before showing responses |
| **ADK Agent Skills** | Orchestrator loads domain knowledge from `SKILL.md` artifacts via `SkillToolset` meta-tools |
| **Multi-Point RAG** | UnderwritingAgent makes 2 targeted queries; LoanDecisionAgent retrieves ECOA guidance — all from a 9-domain regulatory corpus |
| **Repair & Resume** | SQLite workflow management tracks each step; workflow can pause on errors and resume from checkpoint |
| **A2A Agent Card** | `/.well-known/agent-card.json` exposes the agent's 10 capabilities for A2A discovery |

### Agent Flow

```
User message
  └── SmallBusinessLoanOrchestratorAgent
        ├── check_process_status          (SQLite state)
        ├── load_skill("loan-orchestration-protocol")   ← ADK Skill
        ├── AgentTool(DocumentExtractionAgent)  →  LoanApplicationData
        ├── AgentTool(UnderwritingAgent)         →  UnderwritingReport
        │     └── retrieve_underwriting_context()
        │           ├── AutoRAG query 1: eligibility rules
        │           └── AutoRAG query 2: industry risk guidance
        ├── [ELIGIBLE/REVIEW path]
        │     ├── load_skill("loan-pricing-guide")       ← ADK Skill
        │     ├── AgentTool(PricingAgent)         →  PricingResult
        │     └── ── HITL pause: present pricing, await approval ──
        │           └── AgentTool(LoanDecisionAgent) → approval letter
        └── [INELIGIBLE path]
              ├── load_skill("loan-adverse-action")      ← ADK Skill
              └── AgentTool(LoanDecisionAgent)
                    └── finalize_loan_decision()
                          └── AutoRAG query 3: ECOA adverse action guidance
```

### ADK Skills

The orchestrator loads policy documents on demand from the `skills/` directory using `SkillToolset`. Skills are markdown files the LLM fetches with `load_skill(name)` — they contain bank policy, regulatory requirements, and workflow guidance that stays current without code changes.

| Skill | Loaded When |
|---|---|
| `loan-orchestration-protocol` | Start of any new loan application |
| `loan-eligibility-guide` | When explaining eligibility decisions to users |
| `loan-pricing-guide` | After PricingAgent returns results, before presenting to user |
| `loan-adverse-action` | Before LoanDecisionAgent generates a decline letter |

---

## B. Demo Prompts

> **Cluster endpoint:** `https://loan-agent-loan-agent.apps.ocp.qn6c5.sandbox1388.opentlc.com`
>
> Use fresh loan IDs for each demo session to avoid state collisions from prior runs.

### Scenario 1 — Status Check

Check the state of any previously submitted application. Uses only `check_process_status` — fast and lightweight.

```
What is the status of loan application SBL-2026-00201?
```

**Expected tool sequence:** `check_process_status → load_skill`
**Expected response:** Reports whether the application is in-progress, which step it's at, or completed.

---

### Scenario 2 — Complete ELIGIBLE Application (Happy Path)

Paste in one message. The agent runs the full pipeline and pauses for approval after pricing.

```
Process loan application SBL-2026-10001.

Business: Sunrise Bakehouse LLC
Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201
Industry: Retail bakery (NAICS 311811), 5 years in business, 14 employees
Address: 100 Main St, Springfield IL 62701
Financials: $980K annual revenue, $62K net profit, no existing debt
Loan: $180,000 for 60 months to purchase a commercial deck oven and expand production line
Collateral: Baking equipment $140,000 + business assets $85,000
```

**Expected tool sequence:**
```
check_process_status
→ load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent
→ UnderwritingAgent  [2 AutoRAG queries: eligibility + industry]
→ load_skill("loan-pricing-guide")
→ PricingAgent
→ [approval prompt]
```

**Expected outcome:** ELIGIBLE or REVIEW status, Tier 2–3, interest rate 8–10%, monthly payment ~$3,700–$3,800, then pauses for your approval.

Reply **`yes`** to generate the approval letter, or **`no`** to decline.

---

### Scenario 3 — High-Revenue Low-Risk (Tier 1 Approval)

Strong financials, long operating history — should land Tier 1.

```
Process loan application SBL-2026-10002.

Business: Blue Ridge Logistics Inc
Owner: Casey Hartman, casey@blueridgelogistics.com, 555-0202
Industry: Freight logistics (NAICS 484110), 9 years in business, 38 employees
Address: 450 Commerce Blvd, Atlanta GA 30303
Financials: $4.1M annual revenue, $310K net profit, $120K existing debt (equipment lease)
Loan: $500,000 for 84 months to purchase two refrigerated delivery trucks
Collateral: Fleet vehicles and warehouse equipment $680,000
```

**Expected outcome:** ELIGIBLE, Tier 1 Low Risk, ~6–7% APR.

Reply **`yes`** to generate the approval letter.

---

### Scenario 4 — INELIGIBLE Application (Decline Letter)

Gambling business + under 2-year operating history = two hard regulatory bars.

```
Process loan application SBL-2026-10003.

Business: Lucky Stars Casino Lounge
Owner: Alex Rivera, alex@luckystars.com, 555-0301
Industry: Gambling/casino (NAICS 713210), 8 months in business, 5 employees
Address: 500 Vegas Blvd, Las Vegas NV 89101
Financials: $420K annual revenue, $18K net profit, no existing debt
Loan: $300,000 for 60 months for renovations and gaming equipment
Collateral: Gaming equipment $180,000
```

**Expected tool sequence:**
```
check_process_status
→ load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent
→ UnderwritingAgent  [2 AutoRAG queries: eligibility + industry]
→ load_skill("loan-adverse-action")
→ LoanDecisionAgent  [1 AutoRAG query: ECOA adverse action guidance]
   PricingAgent: auto-skipped
```

**Expected outcome:** Decline letter with:
- Gambling industry prohibited under 13 CFR § 120.110
- Operating history < 2-year minimum
- ECOA adverse action notice paragraph
- Reapplication guidance

---

### Scenario 5 — Elevated Risk / Borderline (REVIEW)

Short history, thin margins, but not disqualifying — lands in REVIEW with elevated rate.

```
Process loan application SBL-2026-10004.

Business: Pixel & Grain Photography Studio
Owner: Alex Navarro, alex@pixelandgrain.com, 555-0203
Industry: Commercial photography (NAICS 541922), 2 years in business, 3 employees
Address: 200 Creative Ave, Austin TX 78701
Financials: $210K annual revenue, $18K net profit, no existing debt
Loan: $75,000 for 48 months to purchase camera systems and studio lighting
Collateral: Camera and studio equipment $55,000
```

**Expected outcome:** REVIEW, Tier 3 Elevated Risk, ~9.5–11% APR. Still reaches approval prompt.

---

### Scenario 6 — Missing Fields (Repair & Resume)

Submit incomplete data — the agent halts and lists exactly what's missing.

```
Process loan application SBL-2026-10005.

Business: Mesa Verde Landscaping
Financials: $620K revenue, requesting $120K for 36 months
```

**Expected:** Agent extracts partial data, UnderwritingAgent halts due to missing required fields.

**Resume after providing the missing info:**

```
Resume SBL-2026-10005. Owner is Taylor Brooks, taylor@mesaverdeland.com, 555-0204.
Industry: landscaping and grounds maintenance (NAICS 561730), 6 years in business, 11 employees.
Address: 800 Desert Rd, Tucson AZ 85701.
Net profit $48K, no existing debt. Collateral: landscaping equipment $90K.
```

**Expected:** Agent resumes from the failed step, completes underwriting and pricing.

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
curl -X POST http://localhost:8080/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Process loan application SBL-2026-10001. Business: Sunrise Bakehouse LLC. Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201. Retail bakery, 5 years, 14 employees. Annual revenue $980K, net profit $62K, no debt. Requesting $180K for 60 months for oven purchase. Collateral: baking equipment $140K."
    }],
    "model": "loan-agent"
  }'

# Approve using the session_id from the previous response
curl -X POST http://localhost:8080/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "yes"}],
    "model": "loan-agent",
    "session_id": "<session_id from previous response>"
  }'
```

---

## D. Deployed on RHOAI (AgentSandbox + OpenShell)

The agent runs on Red Hat OpenShift AI as an `agents.x-k8s.io/v1beta1 Sandbox` resource with OpenShell network enforcement. All infrastructure is GitOps-managed via ArgoCD — no manual `oc apply` required.

### Repos

| Repo | Contents |
|---|---|
| `rrbanda/mortgage` | Agent source code, `Containerfile`, `server.py`, `skills/` |
| `rrbanda/ai-platforms` | ArgoCD Applications, AppProjects, all Kubernetes manifests for loan-agent |

### Architecture on Cluster

```
Open WebUI (AgentHive)
  └── /chat/completions  ──►  loan-agent Pod (AgentSandbox)
                                ├── OpenShell supervisor (network enforcement)
                                ├── MaaS → Gemini 2.5 Flash
                                ├── AutoRAG (OGX) → 9-domain regulatory corpus
                                │     └── Milvus vector store (nomic-embed-text-v1.5)
                                ├── Skills (SKILL.md artifacts in skills/)
                                └── SQLite state → PVC (/app/data/state.db)
```

### Quick API Tests (Cluster)

```bash
BASE=https://loan-agent-loan-agent.apps.ocp.qn6c5.sandbox1388.opentlc.com

# Health
curl $BASE/health

# Agent card (A2A discovery — lists all 10 capabilities)
curl $BASE/.well-known/agent-card.json | python3 -m json.tool | head -30

# Status check
curl -s -X POST $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is the status of loan application SBL-2026-00201?"}], "model": "loan-agent"}'
```

### AutoRAG: Multi-Point Regulatory Knowledge Retrieval

The agent makes up to **3 targeted AutoRAG queries** per loan run — pulling only the most relevant policy chunks for each application's specific profile.

| Query | Agent | What it retrieves |
|---|---|---|
| Eligibility rules | UnderwritingAgent | Operating history, DSCR, loan-to-revenue, collateral thresholds |
| Industry risk | UnderwritingAgent | NAICS-specific risk flags, prohibited codes (13 CFR § 120.110) |
| ECOA guidance | LoanDecisionAgent | Adverse action notice requirements, 12 CFR § 1002.9 decline reason codes |

**Corpus (9 documents, ~78KB of actual regulatory text):**

| Domain | Source |
|---|---|
| SBA general eligibility + DSCR | SBA SOP 50 10 v8.1 |
| Collateral requirements + LTV table | SBA SOP 50 10 v8.1 |
| Prohibited business types | 13 CFR § 120.110 (Cornell LII) |
| Adverse action notice requirements | 12 CFR § 1002.9 + Regulation B (Cornell LII) |
| Prohibited NAICS codes (30 codes) | SBA/CFR cross-reference |
| Industry risk assessment guide | Cymbal Bank policy |
| Risk tier + rate guide (Tier 1–4) | Cymbal Bank pricing policy |
| Applicant FAQ (20 Q&A) | Cymbal Bank counseling program |
| Reapplication guidance | SBA Resource Partner Network |

**Current vector store:** `vs_23c69157-2907-4576-8fe0-dc491de89d14`

**Re-seeding after corpus updates:**

```bash
# Run from mortgage/ after updating tools/corpus/**/*.md
AUTORAG_BASE_URL=http://autorag-ogx-service.autorag.svc.cluster.local:8321 \
  python3 tools/seed_autorag.py
# Copy the printed vector_store_id into ai-platforms sandbox.yaml and commit.
```

The ArgoCD PostSync hook Job (`seed-loan-knowledge-base`) re-seeds automatically on each ArgoCD sync when the corpus changes.

**Local fallback (no AutoRAG required):**

When `AUTORAG_BASE_URL` is not set, the agent uses a static `eligibility_rules.json` fallback. No code change needed — `config.using_autorag()` returns `True` only when both env vars are set.

### ADK Skills on Cluster

Skills are loaded from `skills/` in the container image. The orchestrator calls `load_skill(name)` at defined checkpoints — the LLM reads the full `SKILL.md` body and uses it to guide its next actions.

**Verified skill loading sequence (from pod logs):**

```
# ELIGIBLE path
Tool sequence: check_process_status -> load_skill -> DocumentExtractionAgent
               -> UnderwritingAgent -> load_skill -> PricingAgent

# INELIGIBLE path
Tool sequence: check_process_status -> load_skill -> DocumentExtractionAgent
               -> UnderwritingAgent -> load_skill -> LoanDecisionAgent
```

### Secrets (all SealedSecrets — no plaintext in git)

| Secret | Contents |
|---|---|
| `loan-agent-auth` | MaaS API key (`llm-api-key`) |
| `openshell-client-tls` | OpenShell gateway TLS (`ca.crt`, `tls.crt`, `tls.key`) |

### Building and Pushing a New Image

```bash
cd mortgage

podman build --platform linux/amd64 -t small-business-loan-agent:latest -f Containerfile .

REGISTRY=default-route-openshift-image-registry.apps.ocp.qn6c5.sandbox1388.opentlc.com
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

### RHOAI Cluster (set in `ai-platforms` `sandbox.yaml`)

| Variable | Value | Description |
|---|---|---|
| `MAAS_BASE_URL` | `https://maas.apps.ocp.qn6c5.sandbox1388.opentlc.com` | Red Hat MaaS endpoint |
| `MAAS_API_KEY` | from SealedSecret | MaaS API key |
| `MODEL_NAME` | `gemini-2.5-flash` | Model backend |
| `AUTORAG_BASE_URL` | `http://autorag-ogx-service.autorag.svc.cluster.local:8321` | OGX AutoRAG endpoint |
| `AUTORAG_VECTOR_STORE_ID` | `vs_23c69157-2907-4576-8fe0-dc491de89d14` | Seeded regulatory knowledge store |
| `STATE_DB_PATH` | `/app/data/state.db` | SQLite on PVC |
| `AGENT_NAME` | `loan-agent` | Model ID shown in Open WebUI |
| `AGENT_HOST` | `loan-agent-loan-agent.apps.ocp.qn6c5.sandbox1388.opentlc.com` | For A2A agent card |
| `BANK_NAME` | `Cymbal Bank` | Bank name in agent prompts |

---

## F. Customization

- **Prompts:** Each sub-agent has a `prompt.py`. Modify to change agent behavior or bank name references.
- **Skills:** Edit `skills/*/SKILL.md` to update policy guidance without a code change or image rebuild.
- **Corpus:** Add/edit `.md` files under `tools/corpus/` and re-seed AutoRAG.
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
