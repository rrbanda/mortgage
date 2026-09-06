# Mortgage Loan Agent

A multi-agent system built with the [Google Agent Development Kit (ADK)](https://adk.dev/) that automates mortgage loan processing. It demonstrates sequential multi-agent orchestration, human-in-the-loop approval, LLM-as-Judge validation, and SQLite-backed repair & resume — **runs entirely locally with just a Gemini API key**.

## A. Overview & Functionalities

### Agent Details

| Property             | Value                                       |
| -------------------- | ------------------------------------------- |
| **Interaction Type** | Workflow                                    |
| **Complexity**       | Advanced                                    |
| **Agent Type**       | Multi-Agent (1 orchestrator + 4 sub-agents) |
| **Vertical**         | Financial Services                          |
| **Framework**        | ADK                                         |
| **Model**            | Gemini 2.0 Flash (configurable via `MODEL_NAME`) |

### Key Features

| Feature                            | Description                                                                                             |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Multi-Agent Orchestration**      | Orchestrator coordinates 4 specialized sub-agents via `AgentTool` in a sequential workflow              |
| **Multimodal Document Extraction** | Gemini reads loan application PDFs natively                                                             |
| **Structured Output**              | Each sub-agent returns validated Pydantic models via `output_schema` / `output_key`                     |
| **Human-in-the-Loop (HITL)**       | Orchestrator pauses after pricing to present results and wait for explicit user approval                |
| **LLM-as-Judge Gate**              | After-agent callback validates trajectory correctness and data grounding before showing responses       |
| **Repair & Resume**                | SQLite workflow management tracks each step; workflow can pause on errors and resume from checkpoint    |
| **Before/After Callbacks**         | State checks before each sub-agent; state logging and issue detection after each sub-agent              |
| **Before-Tool Callback**           | Process halt check prevents agents from executing when workflow is in error/pending state               |
| **Zero Cloud Dependencies**        | State persisted to a local SQLite file — no Firestore, no GCP required for basic usage                 |

### Example Interaction

```
User: Process this loan application for SBL-2025-02142
      [uploads sample_application_complete.pdf]

Agent: [Calls check_process_status -> initializes new process]
       [Calls DocumentExtractionAgent -> extracts data from PDF]
       [Calls UnderwritingAgent -> validates against internal records, checks eligibility]
       [Calls PricingAgent -> calculates rate based on risk tier]

       Loan Application Summary:
       - Business: Cymbal Coffee Roasters LLC
       - Owner: Jane Doe
       - Loan Amount: $150,000
       - Annual Revenue: $850,000
       - Eligibility: ELIGIBLE
       - Risk Tier: Tier 1 - Low Risk
       - Interest Rate: 6.50%
       - Monthly Payment: $2,940.97
       - Total Interest: $26,458.20

       Do you approve this loan? (yes/no)

User: yes

Agent: [Calls LoanDecisionAgent -> finalizes decision]

       Loan SBL-2025-02142 has been approved.
       Decision letter DL-2025-02142-001 has been generated.
```

## B. Architecture

**Agent flow:**
```
SmallBusinessLoanOrchestratorAgent
  ├── check_process_status (SQLite tool)
  ├── AgentTool(DocumentExtractionAgent)  →  LoanApplicationData
  ├── AgentTool(UnderwritingAgent)         →  UnderwritingReport
  ├── AgentTool(PricingAgent)              →  PricingResult
  └── AgentTool(LoanDecisionAgent)         →  LoanDecisionResult
```

**State machine (SQLite, one row per `loan_request_id`):**
```
Process State
  |-- overall_status: active | pending_approval | completed | failed
  |-- steps:
  |     |-- DocumentExtractionAgent: { status, data, completed_at }
  |     |-- UnderwritingAgent:       { status, data, completed_at }
  |     |-- PricingAgent:            { status, data, completed_at }
  |     |-- LoanDecisionAgent:       { status, data, completed_at }
  |-- issues: [ { step, description, resolved } ]
```

## C. Setup & Running

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A Gemini API key — get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Installation

```bash
git clone https://github.com/rrbanda/mortgage.git
cd mortgage

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and set your GOOGLE_API_KEY
```

### Running the Agent

```bash
uv run adk web
```

Then open `http://localhost:8000`, select `small_business_loan_agent`, upload `data/sample_applications/sample_application_complete.pdf`, and send:

```
Process this loan application for SBL-2025-02142
```

The SQLite state file (`mortgage_agent_state.db`) is created automatically on first run.

### Repair & Resume

When a document has missing fields, the agent stops and records the issue in SQLite. To resume:

1. Open `mortgage_agent_state.db` with any SQLite browser (e.g. [DB Browser for SQLite](https://sqlitebrowser.org/))
2. Find the record for your `loan_request_id`
3. Edit the JSON in `state_json`: fill in the missing field, set the step's `status` to `completed`, and set `overall_status` to `active`
4. Re-submit: `Resume processing for SBL-2025-00391`

## D. Configuration

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | — | **Required.** Gemini API key |
| `MODEL_NAME` | `gemini-2.0-flash` | Model to use for all agents |
| `STATE_DB_PATH` | `./mortgage_agent_state.db` | SQLite database file path |

### Optional: Vertex AI

To use Vertex AI instead of a plain API key, remove `GOOGLE_API_KEY` from `.env` and set:
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

### Optional: GCS document fallback

To enable loading documents from Google Cloud Storage:
```bash
uv sync --extra gcs
```
Then set `GCS_DATA_BUCKET=your-bucket-name` in `.env`.

## E. Customization

- **Prompts:** Each sub-agent has a `prompt.py`. Modify to change agent behavior.
- **Eligibility rules:** Edit `sub_agents/underwriting/eligibility_rules.json`.
- **Mock data:** Replace `MOCK_INTERNAL_RECORDS` in `sub_agents/underwriting/tools.py` with real API calls.
- **Pricing:** Replace `_determine_risk_tier` in `sub_agents/pricing/tools.py` with your pricing engine.

## F. Tests

```bash
uv sync --group dev
uv run pytest tests/unit
```

## License

Copyright 2026 Google LLC. Licensed under the Apache License, Version 2.0.
