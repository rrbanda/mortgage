# Speaker Notes — Loan Processing Agent

### Slide 1: Title

So what I'm going to walk you through today is a production-grade multi-agent system that processes loan applications end-to-end. It's built on Google's Agent Development Kit — ADK — running on OpenShift AI, and it's a good reference architecture because it exercises several platform capabilities in a single workflow: MaaS for model serving, AutoRAG backed by OGX and Milvus for regulatory knowledge retrieval, MLflow for distributed tracing, and the OpenShell sandbox for network-level isolation.

The reason this is interesting from an architecture standpoint isn't any one of those capabilities in isolation — it's the composition pattern. We're running five LlmAgent instances coordinated through ADK's AgentTool mechanism, with four ADK callback hooks enforcing policy at every lifecycle point, an LLM-as-Judge quality gate that validates every response for trajectory correctness and data grounding, and a SQLite dual-write persistence layer that enables repair and resume across pod restarts and session boundaries.

The domain is loan processing — SBA 7(a) loans specifically — which forces you to deal with regulatory compliance, structured output validation, human-in-the-loop approval gates, and the fact that you absolutely cannot hallucinate an interest rate or an eligibility determination. If the agent gets a number wrong, that's a regulatory violation. So every design decision in this system is oriented around correctness, not speed.

---

### Slide 2: At a Glance

At the highest level: a user submits a loan application — could be pasted text, could be a PDF, could be an image — and the agent takes it through a four-stage pipeline. Document extraction, underwriting, pricing, and loan decision. But there are three distinct execution paths depending on the underwriting outcome, and the architecture handles all of them differently.

Path A is the happy path: business is eligible, pricing runs, the orchestrator presents the terms and pauses for human approval — genuine HITL, not a confirmation dialog — and only after explicit consent does LoanDecisionAgent generate a formal approval letter. Path B is the ineligible path: the UnderwritingAgent returns INELIGIBLE, a callback automatically sets a skip flag for PricingAgent, the orchestrator loads the adverse-action skill for ECOA compliance, and LoanDecisionAgent generates a decline letter grounded in actual Regulation B text retrieved from AutoRAG. Path C is the repair path: DocumentExtractionAgent detects missing critical fields, the process halts, the user provides the missing data, and the agent resumes from exactly where it stopped — no re-running completed stages.

The 1+4 architecture: one orchestrator LlmAgent with five tools — a SkillToolset for domain knowledge, check_process_status for state management, and four AgentTool wrappers around the sub-agents. Each sub-agent has its own model context, system prompt, Pydantic output_schema, and isolated tool set. The orchestrator is the only agent with transfer capabilities — sub-agents are locked with disallow_transfer_to_parent and disallow_transfer_to_peers both set to True.

The 9-document AutoRAG corpus covers SBA eligibility, DSCR requirements, collateral and LTV tables, prohibited business types under 13 CFR 120.110, prohibited NAICS codes, industry risk assessment, ECOA adverse action requirements, pricing tier guidance, applicant FAQ, and reapplication guidance. About 78KB of source material seeded into Milvus via a one-time seed_autorag.py script using nomic-embed-text-v1.5 embeddings.

The resume capability is backed by ProcessStateService — a SQLite-based persistence layer on a PVC at /app/data/. Every sub-agent completion writes to both ADK in-memory session state and SQLite. check_process_status is always the first tool call in any turn — it looks up the loan ID, determines the action (proceed, resume, return_status), and reloads completed step data into the fresh ADK session if needed.

---

### Slide 3: Architecture — Why Multiple Agents

The single-agent approach was our first attempt, and it fell apart for three concrete reasons. First, prompt interference — when you put document extraction instructions, underwriting rules, pricing calculations, and letter generation templates in one system prompt, the model starts mixing reasoning modes. We saw it pull field values from the wrong stage, apply pricing logic during underwriting, and hallucinate interest rates before PricingAgent even ran. Second, tool sprawl — a single agent with all eight tools (check_process_status, get_internal_business_data, retrieve_underwriting_context, calculate_loan_pricing, finalize_loan_decision, list_skills, load_skill, load_skill_resource) makes unpredictable tool choices. Third, testability — you can't unit-test underwriting logic if it's entangled with pricing and decision generation.

The ADK AgentTool pattern solves this cleanly. In agent.py, the root_agent is an LlmAgent with five tools: SkillToolset, check_process_status as a standalone function tool, and four AgentTool wrappers — AgentTool(document_extraction_agent), AgentTool(underwriting_agent), AgentTool(pricing_agent), AgentTool(loan_decision_agent). From the orchestrator LLM's perspective, calling "DocumentExtractionAgent" is just a tool call with arguments. But ADK spins up a full LlmAgent with its own system prompt, model context, and output_schema. The sub-agent runs to completion, returns structured output, and ADK writes it to session state under the agent's output_key.

The tool isolation is explicit. UnderwritingAgent's tools list is exactly two items: get_internal_business_data (mock CRM lookup) and retrieve_underwriting_context (the AutoRAG wrapper). PricingAgent has one tool: calculate_loan_pricing. LoanDecisionAgent has one: finalize_loan_decision. None of them have access to each other's tools, to SkillToolset, or to check_process_status. And they're locked down with disallow_transfer_to_parent=True and disallow_transfer_to_peers=True — they can't autonomously decide to call another agent or hand control back.

Each sub-agent also has a Pydantic output_schema — LoanApplicationData, UnderwritingReport, PricingResult, LoanDecisionResult. ADK enforces structured output, so the LLM is constrained to return valid JSON that matches the schema. This is what makes the grounding check in the LLM-as-Judge possible — you can compare the orchestrator's natural language response against the structured agent outputs field by field.

---

### Slide 4: Tool and Skill Access Matrix

This diagram is the access control contract. Top section is LLM-callable tools — what each agent can invoke directly. Green dot means available, empty means not. The orchestrator has check_process_status, AgentTool wrappers, and SkillToolset. DocumentExtractionAgent has zero tools — it's pure extraction from the injected document. UnderwritingAgent has get_internal_business_data and retrieve_underwriting_context. PricingAgent has calculate_loan_pricing. LoanDecisionAgent has finalize_loan_decision.

Bottom section is the critical distinction: internal AutoRAG calls. These are not LLM-visible tools. retrieve_underwriting_context, when called by the LLM, internally makes two separate AutoRAG queries — retrieve_eligibility_rules and retrieve_industry_guidance. finalize_loan_decision internally calls retrieve_regulatory_guidance on the decline path. The LLM never knows these RAG calls happen — it just sees enriched tool responses. Three AutoRAG queries total per loan, none of them LLM-initiated.

The four skills at the bottom — loan-orchestration-protocol, loan-eligibility-guide, loan-pricing-guide, loan-adverse-action — are loaded via SkillToolset and only accessible to the orchestrator. Sub-agents don't know skills exist.

---

### Slide 5: The Pipeline Diagram

Let me walk through the diagram in detail. Everything starts with check_process_status — literally every turn. This tool takes the loan_request_id from session state, queries SQLite via ProcessStateService, and returns one of four actions: "proceed_to_analysis" for new applications, "resume" for partially completed ones, "return_status" for status checks, or "pending_approval" when we're waiting for HITL.

For a new application, the orchestrator loads the loan-orchestration-protocol skill via SkillToolset, then calls AgentTool(DocumentExtractionAgent). The before_model callback — inject_document_into_request — fires here, injecting PDF/image content as a Part in the LLM request. DocumentExtractionAgent has output_schema=LoanApplicationData — a Pydantic model with 13 fields: business_name, owner_name, ein, industry, years_in_business, annual_revenue, net_profit, loan_amount_requested, loan_term_months, collateral_offered, business_address, owner_email, owner_phone.

Next, UnderwritingAgent. This agent has two tools. get_internal_business_data is a mock CRM that returns business registration data. retrieve_underwriting_context is the AutoRAG wrapper — the LLM sees it as one tool call, but internally in sub_agents/underwriting/rag_tools.py, it calls retrieve_eligibility_rules and retrieve_industry_guidance separately. Each makes an httpx POST to /v1/vector_stores/{id}/search with max_num_results=3. The eligibility query is parameterized: "SBA 7(a) loan eligibility requirements for [industry] business with [years] years operating history, annual revenue [X], loan amount [Y]."

The branch point happens in the after_agent callback on UnderwritingAgent. If eligibility_status is INELIGIBLE, the callback writes PricingAgent's step as "skipped" in SQLite and sets a session state skip flag. The before_tool callback on the orchestrator checks this flag and blocks PricingAgent. Belt-and-suspenders — the LLM prompt also says to skip pricing, but the callbacks enforce it programmatically.

For eligible loans, PricingAgent runs calculate_loan_pricing — a deterministic function, not an LLM call. It maps risk tier to rate from config (Tier 1: 6.50%, Tier 2: 7.75%, Tier 3: 9.25%, Tier 4: 11.00%), calculates monthly payment and total interest. Then the orchestrator stops for HITL — process status set to "pending_approval" in SQLite.

For ineligible loans, the orchestrator loads loan-adverse-action skill and calls LoanDecisionAgent. Inside finalize_loan_decision, retrieve_regulatory_guidance automatically queries AutoRAG for ECOA and Reg B text — the LLM never sees this as a separate tool call.

The LLM-as-Judge fires after every orchestrator turn. It's a second litellm.acompletion call with a structured prompt that receives the tool sequence, all agent outputs as JSON, the user's message, and the orchestrator's response. response_format is JudgeVerdict — a Pydantic model with is_valid, trajectory_correct, grounded_in_context, response_complete, and reasoning. If is_valid is false, the response is replaced with a generic error. We fail closed, not open.

---

### Slide 6: AutoRAG

The fundamental question was: where does regulatory knowledge live? Fine-tuning — but regulations change and retraining is expensive. System prompt stuffing — but 78KB of regulatory text burns context window and dilutes the instruction. RAG — retrieve just the relevant chunks at decision time. We went with RHOAI's AutoRAG service backed by OGX.

There are four retrieval functions in shared_libraries/rag_tools.py: retrieve_eligibility_rules, retrieve_industry_guidance, retrieve_regulatory_guidance, and retrieve_pricing_guidance. But not all are LLM-callable tools.

retrieve_eligibility_rules and retrieve_industry_guidance are called internally by retrieve_underwriting_context. The LLM makes one tool call; the vector store sees two separate queries with different query strings optimized for each retrieval task. retrieve_regulatory_guidance is called internally by finalize_loan_decision on the ineligible path. retrieve_pricing_guidance exists but is currently unused — reserved for a future iteration.

Each query hits OGX at /v1/vector_stores/{vector_store_id}/search via httpx POST with max_num_results=3 and a 30-second timeout. Low max_num_results is intentional — focused, high-relevance chunks. Three chunks per query means underwriting gets at most 6 chunks total (2 queries × 3), and the decline path gets 3 more.

The fallback: if AutoRAG is completely unavailable, the before_agent callback for UnderwritingAgent loads eligibility rules from a static eligibility_rules.json and stores them in session state. The _search function handles this gracefully: if using_autorag() returns false, it returns an empty string; if httpx fails, it logs a warning and returns empty. No exceptions propagate.

---

### Slide 7: Callbacks and Safety

ADK gives you four callback hooks on every LlmAgent, and we use all four.

before_agent — extract_request_id_from_request. Scans the user's message for SBL-YYYY-XXXXX via regex (prefix, year width, sequence width configurable in config.py). Stores loan_request_id in session state. Also checks for inline base64-encoded documents and stores them under "inline_document."

before_tool — before_tool_callback_check_process_status. The orchestrator's gate. Checks: is process "halted"? Block and ask for missing info. Is process "completed"? Block and return status. Is tool PricingAgent with skip flag set? Block and return skip message. This is belt-and-suspenders with the prompt. In a financial application, you don't rely on prompt compliance alone for control flow.

before_model — inject_document_into_request. Only on DocumentExtractionAgent. Checks session state for "inline_document", modifies the LlmRequest to inject content as a Part. Multimodal input — PDFs, images, text — all through this single injection point.

after_agent — two separate callbacks. On sub-agents: after_agent_callback_with_state_logging. Three functions: (1) persists output to SQLite via ProcessStateService with full model_dump(), (2) checks for issues like missing critical fields → creates review issue, sets process to "halted", (3) for UnderwritingAgent, if INELIGIBLE → writes PricingAgent step as "skipped" and sets skip flag.

On the orchestrator: llm_judge_gate. Extracts tool sequence from current invocation by iterating session events filtered by invocation_id. Collects all agent outputs, serializes to JSON including Pydantic model_dump(). Builds judge prompt with valid trajectory patterns (new eligible, after approval, ineligible decline, status check, resume) and invalid patterns (missing check_process_status, all four agents in one turn, LoanDecisionAgent without approval). Judge response_format = JudgeVerdict Pydantic model with five fields. Uses same model backend via _build_judge_client_kwargs(). Verdict written to _llm_judge_audit in session state for observability.

If the judge call itself fails — network error, model error — callback catches exception, logs it, returns blocked response. Fail closed, not open.

---

### Slide 8: Data Flow Diagram

This diagram shows what actually happens as data moves through the pipeline. Follow it left-to-right. User request enters the orchestrator, which always starts with check_process_status. On "proceed", DocumentExtractionAgent runs first — pure LLM extraction, no tools. Then UnderwritingAgent with two AutoRAG queries shown explicitly — Query 1 for eligibility rules, Query 2 for industry guidance, each returning ≤3 chunks from the Milvus vector store.

The diamond is the branch point — eligibility status. On ELIGIBLE, we flow through the HITL pause (human approval) to LoanDecisionAgent for an approval letter. On INELIGIBLE, PricingAgent is explicitly SKIPPED — you can see it greyed out — and we go straight to LoanDecisionAgent (DENIED) with a third AutoRAG query for ECOA/Reg B adverse action text.

The bottom bar is critical — Session State. Each agent writes to a named key with its Pydantic model output. DocumentExtractionAgent_output gets LoanApplicationData, UnderwritingAgent_output gets UnderwritingReport plus RAG context, and so on. The note at the bottom: "Parallel write: all outputs also persisted to SQLite via ProcessStateService." That dual-write is what makes repair and resume possible.

---

### Slide 9: Repair and Resume

State management has three layers, and understanding why you need all three matters.

Layer 1: ADK session state. In-memory, scoped to an InMemoryRunner session. When the orchestrator calls AgentTool(UnderwritingAgent), ADK writes output to session state under output_key "UnderwritingAgent_output". Problem: InMemoryRunner stores sessions in a Python dict. Pod restart = gone. Different API session = empty.

Layer 2: SQLite via ProcessStateService. PVC at /app/data/ — configurable via STATE_DB_PATH. Schema: loan_request_id (PK), session_id, overall_status (active/pending_approval/completed/failed), current_step, steps JSON (per-agent: status, completed_at, data with full model_dump(), error_message), issues array. After_agent callback writes on every sub-agent completion.

Layer 3: check_process_status — the bridge. Always first call in any turn. Queries ProcessStateService, returns action. For resume: writes all completed step data back into ADK session state. Orchestrator sees them as if they'd just run, proceeds from next uncompleted step.

Layer 4 (edge case): _load_step_data_from_db() inside finalize_loan_decision. When "yes" arrives in a fresh API session, even check_process_status may not fully propagate to tool_context. So finalize_loan_decision checks each prior output key — DocumentExtractionAgent_output, UnderwritingAgent_output, PricingAgent_output — and if empty, loads from SQLite directly. Three independent fallbacks.

Status transitions are strict: active → pending_approval → completed (or failed). Can't go backwards, can't skip states. Enforced in ProcessStateService methods.

---

### Slide 10: OpenShift AI Deployment Architecture

This is the pod-level view. The agent runs as a FastAPI container on OpenShift AI with an OpenShell init container handling network isolation — it sets up egress rules so the pod can only reach MaaS Gateway and AutoRAG endpoints, nothing else. The ConfigMap injects MODEL_NAME, MAAS_BASE_URL, AUTORAG_BASE_URL, AUTORAG_VECTOR_STORE_ID, BANK_NAME, rate tier values, and DEFAULT_LOAN_TERM_MONTHS. SealedSecrets handle MAAS_API_KEY and OpenShell TLS certs.

The PVC at /app/data/ holds state.db — the SQLite database backing ProcessStateService. This is what survives pod restarts. The container image is built from a standard Containerfile with FastAPI, uvicorn, and all dependencies. Endpoints exposed: /chat/completions and /v1/chat/completions for OpenAI-compatible chat, /health for readiness probes, and /.well-known/agent-card.json for A2A agent discovery.

---

### Slide 11: External Connectivity

This diagram shows the three external connections the agent pod makes. First, MaaS Gateway — the agent's model factory in gemini_custom.py calls get_model(), which checks config.using_maas(). If MAAS_BASE_URL and MAAS_API_KEY are set, it returns MaaSLiteLlm wrapping LiteLLM with a URL path template (/gemini-external/{model}/v1). All five agents and the LLM-as-Judge use this same factory. Important production detail: MaaS returns gzip+chunked encoding that triggers an httpcore read-stall bug, so we force "Accept-Encoding: identity" on all requests.

Second, AutoRAG (OGX) — rag_tools.py uses httpx with a 30-second timeout to POST queries to /v1/vector_stores/{id}/search. The Milvus vector store uses nomic-embed-text-v1.5 embeddings across a 9-document regulatory corpus.

Third, SQLite state.db on PVC — not an external service, but persistent storage that outlives the pod. state_service.py uses sqlite3 directly.

The Open WebUI (AgentHive) connection shows the ingress — users talk to the agent via /chat/completions endpoints. This is an OpenAI-compatible API, so any client that speaks the completions protocol works.

---

### Slide 12: RHOAI Capabilities

Model Serving — MaaS. The model factory in gemini_custom.py has get_model() that checks config.using_maas() — bool(MAAS_BASE_URL and MAAS_API_KEY). If true, returns MaaSLiteLlm from the rh-maas-litellm package — custom ADK model class wrapping LiteLLM with MaaS config: base URL, API key, URL path template. If MaaS isn't configured, falls back to GeminiPreview — subclass of ADK's Gemini supporting both GOOGLE_API_KEY and GCP ADC. All five agents and the judge use the same factory. Change MAAS_BASE_URL in ConfigMap → entire system switches backends, no code change.

AutoRAG — OGX. Two env vars: AUTORAG_BASE_URL, AUTORAG_VECTOR_STORE_ID. API: POST to /v1/vector_stores/{id}/search, JSON body with query and max_num_results. httpx with 30-second timeout, configurable SSL. Corpus seeded via tools/seed_autorag.py from tools/corpus/ — 9 markdown files by domain.

MLflow Tracing. In tracing.py: enable_tracing() called in FastAPI lifespan handler. Checks MLFLOW_TRACKING_URI — absent = silently skipped. Present = health check → mlflow.set_tracking_uri() → set_experiment() → config.enable_async_logging() → mlflow.litellm.autolog(). That autolog call monkey-patches LiteLLM so every completion generates spans with prompts, responses, latency, token counts. Both agent calls and judge go through LiteLLM → full pipeline observability.

Deployment: Containerfile builds FastAPI image. OpenShell init container for network isolation. ConfigMap for tunables. SealedSecrets for credentials. PVC for SQLite state.

Note: EvalHub integration not in this version. Agent uses ADK's adk eval for smoke tests and LLM-as-Judge for runtime quality. EvalHub with systematic eval datasets is on the roadmap.

---

### Slide 13: Skills

Important distinction between skills and RAG. Skills are workflow knowledge — they tell the LLM how to behave. RAG is reference knowledge — factual grounding for specific decisions.

Skills are markdown files in /skills/ at repo root — one subdirectory per skill with SKILL.md. In agent.py, load_skills_from_dir reads the directory, SkillToolset wraps them providing three tools: list_skills, load_skill, load_skill_resource. SkillToolset is first in the orchestrator's tools array — skills before action tools. The LLM decides when to load based on context.

The orchestration protocol defines the exact step-by-step workflow. The eligibility guide has five SBA rules with specific thresholds. The pricing guide has tier table and user presentation template. The adverse-action skill has ECOA requirements and decline letter template.

Access control is strict. Only the orchestrator has SkillToolset. Sub-agents cannot load or discover skills. disallow_transfer_to_parent=True, disallow_transfer_to_peers=True on all sub-agents. They process input, produce structured output, return. The orchestrator decides what happens next.

Skills are baked into the container at /app/skills/. Updating = rebuild image, ArgoCD syncs. Different from RAG corpus, which updates via re-running seed_autorag.py without code change. Skills change behavior (workflow, formatting). RAG changes factual basis. They evolve at different rates and should be managed separately.

---

### Slide 14: In Practice

Tracing through the exact tool sequence. User submits "Process loan SBL-2026-10001: Acme Bakery..." before_agent callback parses "SBL-2026-10001" via regex, stores in session state.

Turn 1: check_process_status → ProcessStateService.get_process_status("SBL-2026-10001") → null → create_process() → {action: "proceed_to_analysis"}. load_skill("loan-orchestration-protocol"). AgentTool(DocumentExtractionAgent) → LoanApplicationData{business_name: "Acme Bakery", annual_revenue: 420000, loan_amount_requested: 150000, ...} → SQLite write.

AgentTool(UnderwritingAgent) → before_agent loads eligibility_rules.json. LLM calls get_internal_business_data("Acme Bakery") → mock CRM. LLM calls retrieve_underwriting_context → internally: retrieve_eligibility_rules POST to OGX → 3 chunks; retrieve_industry_guidance POST → 3 chunks. Returns UnderwritingReport{eligibility_status: "ELIGIBLE", risk_flags: ["moderate_debt_ratio"]} → SQLite write.

load_skill("loan-pricing-guide"). AgentTool(PricingAgent) → calculate_loan_pricing() deterministic: Tier 2 → 7.75% → $3,012.43/mo → PricingResult → SQLite write, overall_status → "pending_approval".

Orchestrator presents pricing, asks approval → LLM-as-Judge: trajectory valid, all numbers grounded, response complete → JudgeVerdict{is_valid: true}. Response passes.

Turn 2: "Yes, approve it." check_process_status → reload from SQLite → loads three prior outputs into session. AgentTool(LoanDecisionAgent) → finalize_loan_decision → _load_step_data_from_db fallback if needed → approval letter → LoanDecisionResult{decision: "APPROVED"} → SQLite mark_process_complete. Judge validates. Done.

Two user turns. Behind the scenes: 2 check_process_status, 2 skill loads, 4 sub-agent invocations, 2 AutoRAG queries, 1 CRM lookup, 1 deterministic pricing calc, 2 judge validations, 8 SQLite writes.

---

### Slide 15: Closing

Key architectural takeaways. Multi-agent works when the problem has genuinely distinct reasoning stages — document extraction, underwriting, pricing, letter generation require different prompts, tools, and output schemas. AgentTool makes this clean.

Callbacks are your policy enforcement layer. Don't rely on prompt compliance alone for control flow in financial applications. The prompt says skip pricing for ineligible loans. The callback enforces it programmatically. Belt and suspenders.

LLM-as-Judge adds latency — second LLM call every turn — but for correctness-critical domains it's non-negotiable. Structured JudgeVerdict gives you machine-readable audit trails. Fails closed.

State persistence needs three layers: in-memory for speed, persistent storage for durability, synchronization mechanism to bridge them, plus a last-resort fallback for edge cases.

RHOAI capabilities — MaaS, AutoRAG, MLflow — are structural, not bolt-ons. MaaS serves all five agents and the judge. AutoRAG provides regulatory grounding. MLflow provides observability across a pipeline where one user turn generates six LLM calls.

Everything is in the repo. Happy to go deep on any of these areas.
