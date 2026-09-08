# Demo Speaker Notes

Tell-Show-Tell format for each architecture diagram. Use these as talking points when presenting the Small Business Loan Agent.

---

## Diagram 1: OpenShift Deployment Architecture

### TELL (set the context)

"This agent runs as a single pod on OpenShift, deployed via ArgoCD GitOps. It's built on Google's Agent Development Kit — ADK — and packaged as a standard container image with everything baked in: the agent code, 4 specialized skills for bank policy, 9 regulatory documents for the RAG knowledge base, and a FastAPI server exposing an OpenAI-compatible API. There's no complex infrastructure — just a pod, ConfigMap env vars for tuning, and SealedSecrets for the MaaS API key and OpenShell TLS certs."

### SHOW (walk through the diagram)

- **Open WebUI (AgentHive)** connects through an OpenShift Route with TLS termination — the agent's chat interface looks and feels like any standard chat app
- **One endpoint** is exposed on port 8080: the FastAPI server handles `/chat/completions` (OpenAI-compatible), `/v1/chat/completions`, `/health`, and `/.well-known/agent-card.json` for A2A discovery
- **The pod** runs the Loan Agent container with the OpenShell supervisor installed as an init container for network enforcement
- **ConfigMap** controls model name, AutoRAG endpoint, bank name, interest rate tiers — all operator-tunable without a code change
- **Two SealedSecrets**: `loan-agent-auth` holds the MaaS API key, `openshell-client-tls` holds the gateway TLS certs — never plaintext in git
- **PVC** at `/app/data/` persists the SQLite state database across pod restarts — this is what enables repair & resume
- **Skills are baked into the image** at `/app/skills/` — 4 markdown policy documents the LLM loads on demand
- **Backend connections**: MaaS Gateway for Gemini 2.5 Flash, AutoRAG (OGX) with Milvus vector store for regulatory knowledge retrieval

### TELL (key takeaway)

"The deployment is intentionally simple. One pod, GitOps-managed, with all intelligence in the agent prompts, skills, and regulatory corpus — not in complex infrastructure. Update a skill markdown file, rebuild the image, ArgoCD syncs. Change a rate tier, update the ConfigMap. The agent adapts without touching Python code."

---

## Diagram 2: Multi-Agent Sequential Architecture

### TELL (set the context)

"This is not a simple chatbot. It's a 5-agent system — one orchestrator coordinating four specialist sub-agents in a sequential pipeline. The orchestrator uses ADK's AgentTool pattern to call each sub-agent as a tool, passing data through session state. There are three distinct workflow paths depending on the underwriting outcome, and every path has safety gates."

### SHOW (walk through the diagram)

- **Before anything runs**: The `extract_request_id_from_request` callback extracts the loan ID (SBL-YYYY-XXXXX) from the user's message. No ID, no processing
- **check_process_status** is ALWAYS the first tool call. It checks SQLite: is this a new application, a resume, a status check, or already completed? This is the repair & resume mechanism
- **load_skill("loan-orchestration-protocol")** — the orchestrator loads the full workflow protocol as domain knowledge before doing anything. This keeps the LLM on-script
- **DocumentExtractionAgent** — Gemini's multimodal capability reads the loan application (text or PDF). The `inject_document_into_request` before-model callback handles the document injection. Returns a structured `LoanApplicationData` Pydantic model
- **UnderwritingAgent** — makes TWO AutoRAG queries: one for SBA eligibility rules matching this application's profile, one for industry-specific risk guidance. Falls back to static JSON rules if AutoRAG isn't configured. Returns an `UnderwritingReport` with ELIGIBLE, INELIGIBLE, or REVIEW
- **The branch point** — this is critical:
  - **ELIGIBLE/REVIEW**: PricingAgent calculates the rate, then the orchestrator STOPS and asks "Do you approve?" — genuine HITL
  - **INELIGIBLE**: PricingAgent is auto-skipped (both in the before-tool callback and after-agent state callback), the orchestrator loads the adverse-action skill, and LoanDecisionAgent generates an ECOA-compliant decline letter with a third RAG query for regulatory guidance
- **LLM-as-Judge** — after EVERY orchestrator response, the `llm_judge_gate` makes a second LLM call that checks trajectory correctness, data grounding, and completeness. If it fails, the response is blocked. This is a financial application — wrong numbers are unacceptable

### TELL (key takeaway)

"Four agents, each with a focused job. DocumentExtraction reads the paperwork. Underwriting checks the rules. Pricing calculates the terms. LoanDecision writes the letter. The orchestrator keeps them in sequence, the HITL pause ensures a human approves, and the LLM-as-Judge ensures no hallucinated data reaches the user. And if anything breaks — missing fields, pod restart — the SQLite state lets you resume from exactly where you left off."

---

## Diagram 3: External Connectivity

### TELL (set the context)

"The agent connects to three backend systems, each independently configurable. The architecture supports three different LLM backends — you can switch between MaaS, a plain Gemini API key, or Vertex AI without changing a line of code."

### SHOW (walk through the diagram)

- **Center: Agent Pod** — contains four key modules: `server.py` (FastAPI entry point), `agent.py` (orchestrator definition), `gemini_custom.py` (model factory), `rag_tools.py` (AutoRAG client), and `state_service.py` (SQLite state)
- **MaaS Gateway** (top-right) — the default LLM backend. The `gemini_custom.py` model factory checks environment variables in priority order: MaaS first, then Gemini API key, then Vertex AI. The `rh-maas-litellm` package handles the OpenAI-compatible translation. Both the agents and the LLM-as-Judge callback use the same model backend
- **AutoRAG OGX** (bottom-right) — the regulatory knowledge base. Milvus vector store with `nomic-embed-text-v1.5` embeddings, seeded with 9 markdown documents covering SBA eligibility, CFR regulations, NAICS codes, ECOA requirements, pricing tiers, and FAQs. Three retrieval functions make targeted queries: eligibility rules, industry guidance, and regulatory guidance
- **SQLite State DB** (bottom-left) — process state persisted to a PVC. Tracks each step's status, stores completed agent outputs, and enables resume after pod restarts or human intervention. This is the foundation of the repair & resume capability
- **Open WebUI** (left) — the chat frontend. Connects to the agent via the standard `/chat/completions` endpoint. The agent responds with streaming SSE or synchronous JSON — both are supported

### TELL (key takeaway)

"The key design decision is graceful degradation. No AutoRAG? The agent falls back to static eligibility rules — it still works. No MaaS? Set a Gemini API key instead. The agent adapts to what's available, and the config module is the single source of truth for all environment variables."

---

## Diagram 4: Tool and Skill Access Matrix

### TELL (set the context)

"Not every agent needs every tool. We follow the principle of least privilege — each sub-agent only gets the tools it needs for its specific job. The orchestrator is the only agent with AgentTool wrappers and the SkillToolset. Sub-agents are locked down with `disallow_transfer_to_parent` and `disallow_transfer_to_peers` — they can't autonomously transfer control."

### SHOW (walk through the diagram)

- **Orchestrator** gets everything: `check_process_status` for state management, `AgentTool` wrappers for all 4 sub-agents, and `SkillToolset` for loading domain knowledge. It's the conductor
- **DocumentExtractionAgent** has NO tools — it relies entirely on Gemini's multimodal capability to extract structured data from the document. The `inject_document_into_request` before-model callback handles getting the document into the LLM request
- **UnderwritingAgent** gets exactly two tools: `get_internal_business_data` to fetch mock CRM records, and `retrieve_underwriting_context` which makes two targeted AutoRAG queries. It cannot call any other agent or skip steps
- **PricingAgent** gets one tool: `calculate_loan_pricing`. It reads application and underwriting data from session state, determines the risk tier, and calculates the amortization. No access to external systems
- **LoanDecisionAgent** gets one tool: `finalize_loan_decision`. On the decline path, this tool internally calls `retrieve_regulatory_guidance` for ECOA text. On the approval path, it generates the approval letter with conditions
- **Skills** — only the orchestrator can call `load_skill`. 4 skills covering workflow protocol, eligibility rules, pricing guidance, and adverse action notice requirements. Each loaded at a specific checkpoint in the workflow

### TELL (key takeaway)

"This isn't just organization — it's safety. DocumentExtractionAgent can't call underwriting tools. PricingAgent can't generate decision letters. Each agent stays in its lane. The callbacks enforce prerequisites — you can't reach PricingAgent without completing underwriting first. And the HITL pause means no approval letter is generated without a human saying yes."

---

## Diagram 5: Data Flow Through the Pipeline

### TELL (set the context)

"Let me walk you through exactly what happens when you say 'Process loan application SBL-2026-10001' — from the first word to the final decision letter. Every piece of data flows through ADK session state keys AND gets persisted to SQLite. This dual-write is what makes repair & resume possible."

### SHOW (walk through the diagram)

- **User submits the application** — the before-agent callback extracts `SBL-2026-10001` and stores it as `loan_request_id` in session state
- **check_process_status** — looks up SQLite. New application? Initialize the process, set `overall_status=active`. Returning? Load all completed step data back into session state and tell the orchestrator where to resume
- **DocumentExtractionAgent** — extracts structured data into `DocumentExtractionAgent_output`: business name, financials, loan details. This is a Pydantic `LoanApplicationData` model. The after-agent callback persists it to SQLite
- **UnderwritingAgent** — reads the extraction output, calls two AutoRAG queries, and writes `UnderwritingAgent_output`: eligibility status, risk flags, matched rule. Critical branch point: if INELIGIBLE, the after-agent callback auto-skips PricingAgent in SQLite
- **PricingAgent** (ELIGIBLE/REVIEW only) — reads both prior outputs from session state, calculates risk tier and rate, writes `PricingAgent_output`: interest rate, monthly payment, total interest, risk tier
- **HITL pause** — the orchestrator uses EXACT values from the output keys to present the summary. The LLM-as-Judge validates these values aren't hallucinated
- **LoanDecisionAgent** — reads ALL prior output keys, generates the official letter. Writes `LoanDecisionAgent_output`: decision, letter ID, conditions. The after-agent callback calls `mark_process_complete` — SQLite `overall_status` → `completed`
- **Session State bar** at the bottom shows accumulation: each key builds on the previous. The `_llm_judge_audit` key records the judge's verdict for audit trails

### TELL (key takeaway)

"The key insight is the dual-write architecture. ADK session state gives the agents fast in-memory access to prior results. SQLite gives the system durability across pod restarts and human intervention delays. If the user walks away after pricing and comes back tomorrow, `check_process_status` reloads everything from SQLite into a fresh session and continues from the approval step. Nothing is lost."

---

## Live Demo Flow

After the slides, transition to the live demo with:

"Now let me show you this in action. I'll walk through three scenarios — a happy-path approval, an ineligible decline, and a repair-and-resume — to demonstrate the full capability of the agent."

### Demo Script

**1. Status check (30 seconds)**
> Prompt: `What is the status of loan application SBL-2026-00201?`

Agent calls `check_process_status`. Shows whether the application exists, its current step, and overall status.

**2. Happy path — ELIGIBLE application (3-5 minutes)**
> Prompt:
> ```
> Process loan application SBL-2026-10001.
>
> Business: Sunrise Bakehouse LLC
> Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201
> Industry: Retail bakery (NAICS 311811), 5 years in business, 14 employees
> Address: 100 Main St, Springfield IL 62701
> Financials: $980K annual revenue, $62K net profit, no existing debt
> Loan: $180,000 for 60 months to purchase a commercial deck oven
> Collateral: Baking equipment $140,000 + business assets $85,000
> ```

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ load_skill("loan-pricing-guide") → PricingAgent → [STOP: approval prompt]
```

**Expected outcome:** ELIGIBLE, Tier 2 Moderate Risk, ~7.75% APR, monthly payment ~$3,636. Pauses for approval.

Reply **`yes`** to generate the approval letter with decision letter ID.

**3. Decline path — INELIGIBLE application (2-3 minutes)**
> Prompt:
> ```
> Process loan application SBL-2026-10003.
>
> Business: Lucky Stars Casino Lounge
> Owner: Alex Rivera, alex@luckystars.com, 555-0301
> Industry: Gambling/casino (NAICS 713210), 8 months in business, 5 employees
> Address: 500 Vegas Blvd, Las Vegas NV 89101
> Financials: $420K annual revenue, $18K net profit, no existing debt
> Loan: $300,000 for 60 months for renovations and gaming equipment
> Collateral: Gaming equipment $180,000
> ```

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ PricingAgent SKIPPED
→ load_skill("loan-adverse-action") → LoanDecisionAgent [1 AutoRAG query]
```

**Expected outcome:** INELIGIBLE decline letter citing gambling industry prohibition (13 CFR § 120.110) and operating history < 2 years. ECOA-compliant adverse action notice. No approval prompt — decline is immediate.

**4. Repair & resume (2-3 minutes)**
> Prompt (incomplete):
> ```
> Process loan application SBL-2026-10005.
>
> Business: Mesa Verde Landscaping
> Financials: $620K revenue, requesting $120K for 36 months
> ```

**Expected:** Agent extracts partial data, halts with missing fields list.

> Resume prompt:
> ```
> Resume SBL-2026-10005. Owner is Taylor Brooks, taylor@mesaverdeland.com, 555-0204.
> Industry: landscaping (NAICS 561730), 6 years, 11 employees.
> Address: 800 Desert Rd, Tucson AZ 85701.
> Net profit $48K, no existing debt. Collateral: landscaping equipment $90K.
> ```

**Expected:** `check_process_status` loads the completed DocumentExtractionAgent data from SQLite, resumes from UnderwritingAgent, completes the full pipeline.

### Key Talking Points During Demo

- "Notice `check_process_status` is always the first tool call — it's the state machine entry point"
- "The orchestrator loaded `loan-orchestration-protocol` skill before calling any agents — it's reading the bank's workflow protocol"
- "Two AutoRAG queries in underwriting — one for eligibility policy, one for industry risk. These are targeted, not generic"
- "The HITL pause is real — the orchestrator stops and waits for my explicit 'yes' before generating the approval letter"
- "For the decline, notice PricingAgent was automatically skipped — the before-tool callback saw INELIGIBLE and blocked it"
- "The LLM-as-Judge checked the response before I saw it — trajectory correct, data grounded, response complete"
- "On the resume, `check_process_status` reloaded the completed extraction data from SQLite into the fresh session — no data loss"
