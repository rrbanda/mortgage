# Test Prompts

Categorized test prompts for the Loan Agent. Each prompt includes
the expected tool sequence and outcome so testers know what to verify in the response.

---

## 1. Status Checks

### 1.1 Check Status of an Existing Application

**Prompt:**
> What is the status of loan application SBL-2026-00201?

**Expected tool sequence:** `check_process_status`

**Expected behavior:**
- Agent calls `check_process_status` with the extracted loan ID
- Returns one of: not found, active (in-progress), pending_approval, completed, or failed
- Reports the current step and overall status
- Does NOT proceed with any sub-agents

### 1.2 Check Status of a Non-Existent Application

**Prompt:**
> What is the status of loan application SBL-2026-99999?

**Expected tool sequence:** `check_process_status`

**Expected behavior:**
- `check_process_status` initializes a new process (since the ID doesn't exist)
- Returns `action: "proceed_to_analysis"` — but the agent should report the status, not start processing (no application data provided)
- Agent should explain that a new process was initialized and ask for application details

### 1.3 No Loan ID Provided

**Prompt:**
> Can you help me with a loan application?

**Expected behavior:**
- `extract_request_id_from_request` callback fails to find a loan ID
- Returns a helpful message explaining the required format: `SBL-YYYY-XXXXX`
- Does NOT call any tools

---

## 2. Happy Path — ELIGIBLE Applications

### 2.1 Strong Business (Tier 1 — Low Risk)

**Prompt:**
> Process loan application SBL-2026-10002.
>
> Business: Blue Ridge Logistics Inc
> Owner: Casey Hartman, casey@blueridgelogistics.com, 555-0202
> Industry: Freight logistics (NAICS 484110), 9 years in business, 38 employees
> Address: 450 Commerce Blvd, Atlanta GA 30303
> Financials: $4.1M annual revenue, $310K net profit, $120K existing debt (equipment lease)
> Loan: $500,000 for 84 months to purchase two refrigerated delivery trucks
> Collateral: Fleet vehicles and warehouse equipment $680,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ load_skill("loan-pricing-guide") → PricingAgent → [STOP: approval prompt]
```

**Expected outcome:**
- DocumentExtractionAgent: All fields extracted, business_name="Blue Ridge Logistics Inc", annual_revenue="$4.1M" or "$4,100,000"
- UnderwritingAgent: ELIGIBLE (revenue >$500K, 9+ years, low LTR)
- PricingAgent: Tier 1 — Low Risk, ~6.50% APR (no risk flags → Tier 1)
- Agent presents pricing and asks "Do you approve?"
- Reply **`yes`** to generate approval letter with decision letter ID

### 2.2 Moderate Business (Tier 2 — Moderate Risk)

**Prompt:**
> Process loan application SBL-2026-10001.
>
> Business: Sunrise Bakehouse LLC
> Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201
> Industry: Retail bakery (NAICS 311811), 5 years in business, 14 employees
> Address: 100 Main St, Springfield IL 62701
> Financials: $980K annual revenue, $62K net profit, no existing debt
> Loan: $180,000 for 60 months to purchase a commercial deck oven and expand production line
> Collateral: Baking equipment $140,000 + business assets $85,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ load_skill("loan-pricing-guide") → PricingAgent → [STOP: approval prompt]
```

**Expected outcome:**
- UnderwritingAgent: ELIGIBLE (revenue >$500K, 5 years, LTR ~18%)
- PricingAgent: Tier 2 — Moderate Risk, ~7.75% APR (ELIGIBLE with risk flags from underwriting discrepancies against mock records)
- Monthly payment ~$3,636, total interest ~$38,143
- Agent pauses for approval

### 2.3 Borderline Business (Tier 3 — Elevated Risk)

**Prompt:**
> Process loan application SBL-2026-10004.
>
> Business: Pixel & Grain Photography Studio
> Owner: Alex Navarro, alex@pixelandgrain.com, 555-0203
> Industry: Commercial photography (NAICS 541922), 2 years in business, 3 employees
> Address: 200 Creative Ave, Austin TX 78701
> Financials: $210K annual revenue, $18K net profit, no existing debt
> Loan: $75,000 for 48 months to purchase camera systems and studio lighting
> Collateral: Camera and studio equipment $55,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ load_skill("loan-pricing-guide") → PricingAgent → [STOP: approval prompt]
```

**Expected outcome:**
- UnderwritingAgent: REVIEW (revenue $200K–$500K, 2 years, matches rule_002)
- PricingAgent: Tier 3 — Elevated Risk, ~9.25% APR
- Agent still reaches approval prompt (REVIEW is not a rejection)

---

## 3. Decline Path — INELIGIBLE Applications

### 3.1 Prohibited Industry (Gambling)

**Prompt:**
> Process loan application SBL-2026-10003.
>
> Business: Lucky Stars Casino Lounge
> Owner: Alex Rivera, alex@luckystars.com, 555-0301
> Industry: Gambling/casino (NAICS 713210), 8 months in business, 5 employees
> Address: 500 Vegas Blvd, Las Vegas NV 89101
> Financials: $420K annual revenue, $18K net profit, no existing debt
> Loan: $300,000 for 60 months for renovations and gaming equipment
> Collateral: Gaming equipment $180,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ PricingAgent SKIPPED
→ load_skill("loan-adverse-action") → LoanDecisionAgent [1 AutoRAG query: ECOA guidance]
```

**Expected outcome:**
- UnderwritingAgent: INELIGIBLE with risk flags:
  - Gambling industry prohibited under 13 CFR § 120.110
  - Operating history < 2 years (8 months < 1 year minimum)
- PricingAgent: Auto-skipped (before-tool callback detects INELIGIBLE)
- LoanDecisionAgent: DENIED decision, decline letter including:
  - Specific decline reasons in plain English
  - ECOA adverse action notice paragraph (if AutoRAG available)
  - Decision letter reference ID (e.g., `DL-2026-10003-001`)
  - Reapplication guidance
- NO approval prompt — decline is immediate

### 3.2 Insufficient Operating History Only

**Prompt:**
> Process loan application SBL-2026-10010.
>
> Business: Fresh Start Juicery
> Owner: Maya Chen, maya@freshstartjuice.com, 555-0401
> Industry: Juice bar (NAICS 722515), 6 months in business, 2 employees
> Address: 1200 Health Blvd, San Diego CA 92101
> Financials: $85K annual revenue, $5K net profit, no existing debt
> Loan: $50,000 for 36 months for equipment and working capital
> Collateral: Commercial juicing equipment $30,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ PricingAgent SKIPPED
→ load_skill("loan-adverse-action") → LoanDecisionAgent [1 AutoRAG query]
```

**Expected outcome:**
- UnderwritingAgent: INELIGIBLE (6 months < 1 year minimum — rule_003)
- Decline letter citing insufficient operating history
- Invite to reapply after reaching 1 year of operations

### 3.3 Excessive Loan-to-Revenue Ratio

**Prompt:**
> Process loan application SBL-2026-10011.
>
> Business: Small Town Repairs LLC
> Owner: Jake Morrison, jake@smalltownrepairs.com, 555-0501
> Industry: General maintenance (NAICS 811490), 4 years in business, 6 employees
> Address: 300 Industrial Rd, Columbus OH 43215
> Financials: $180K annual revenue, $22K net profit, no existing debt
> Loan: $200,000 for 60 months for workshop expansion
> Collateral: Workshop equipment $100,000

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent → UnderwritingAgent [2 AutoRAG queries]
→ PricingAgent SKIPPED
→ load_skill("loan-adverse-action") → LoanDecisionAgent [1 AutoRAG query]
```

**Expected outcome:**
- UnderwritingAgent: INELIGIBLE (LTR = $200K/$180K = 111% > 75% threshold — rule_004)
- Decline letter citing excessive loan-to-revenue ratio

---

## 4. Repair & Resume

### 4.1 Missing Fields — Initial Submission

**Prompt:**
> Process loan application SBL-2026-10005.
>
> Business: Mesa Verde Landscaping
> Financials: $620K revenue, requesting $120K for 36 months

**Expected tool sequence:**
```
check_process_status → load_skill("loan-orchestration-protocol")
→ DocumentExtractionAgent
```

**Expected behavior:**
- DocumentExtractionAgent extracts partial data (business_name, annual_revenue, loan_amount, loan_term)
- `_check_for_issues` detects missing critical fields: owner_name, possibly others
- Step marked for review in SQLite (`overall_status: pending_approval`)
- Agent reports exactly which fields are missing and asks the user to provide them

### 4.2 Missing Fields — Resume with Complete Data

**Prompt (same session or new session):**
> Resume SBL-2026-10005. Owner is Taylor Brooks, taylor@mesaverdeland.com, 555-0204.
> Industry: landscaping and grounds maintenance (NAICS 561730), 6 years in business, 11 employees.
> Address: 800 Desert Rd, Tucson AZ 85701.
> Net profit $48K, no existing debt. Collateral: landscaping equipment $90K.

**Expected tool sequence:**
```
check_process_status (loads completed step data, identifies resume point)
→ [resume from next step] → UnderwritingAgent [2 AutoRAG queries]
→ load_skill("loan-pricing-guide") → PricingAgent → [STOP: approval prompt]
```

**Expected behavior:**
- `check_process_status` finds the existing process, loads DocumentExtractionAgent data from SQLite
- Identifies `next_step_to_execute` — resumes from where the workflow halted
- Completes underwriting and pricing with the full data
- Pauses for approval

---

## 5. Multi-Turn Approval Flow

### 5.1 Approve After Pricing

**Prompt (after receiving pricing summary):**
> yes

**Expected tool sequence:** `LoanDecisionAgent`

**Expected behavior:**
- LoanDecisionAgent calls `finalize_loan_decision`
- Returns APPROVED decision with:
  - Decision letter ID (e.g., `DL-2026-10001-001`)
  - Approved amount, rate, and term from prior agent outputs
  - Conditions: insurance verification within 30 days, collateral documentation
- SQLite status updated to `completed`

### 5.2 Reject After Pricing

**Prompt (after receiving pricing summary):**
> no

**Expected behavior:**
- Orchestrator acknowledges the rejection
- Does NOT call LoanDecisionAgent
- Informs user that the application will not proceed
- No decision letter generated

---

## 6. Skill Loading Verification

### 6.1 Verify Orchestration Protocol Loads

**What to watch for in tool calls:**
- `load_skill("loan-orchestration-protocol")` should appear BEFORE `DocumentExtractionAgent` on every new application
- Contains the full workflow protocol with step-by-step instructions

### 6.2 Verify Pricing Guide Loads

**What to watch for in tool calls:**
- `load_skill("loan-pricing-guide")` should appear AFTER `UnderwritingAgent` and BEFORE presenting pricing to the user
- Contains risk tier table and presentation format

### 6.3 Verify Adverse Action Guide Loads

**What to watch for in tool calls:**
- `load_skill("loan-adverse-action")` should appear AFTER `UnderwritingAgent` returns INELIGIBLE and BEFORE `LoanDecisionAgent`
- Contains ECOA requirements and decline letter template

### 6.4 List Available Skills

**Prompt:**
> What skills do you have available?

**Expected behavior:**
- Orchestrator calls `list_skills` (from SkillToolset)
- Returns 4 skills: loan-orchestration-protocol, loan-eligibility-guide, loan-pricing-guide, loan-adverse-action
- Each with name and description

---

## 7. Edge Cases

### 7.1 Duplicate Application ID

**Prompt (after a previous run with the same ID):**
> Process loan application SBL-2026-10001.
>
> Business: Sunrise Bakehouse LLC
> ...

**Expected behavior:**
- `check_process_status` finds the existing completed process
- Returns `action: "completed"` or `action: "return_status"`
- Agent reports the application is already processed
- Does NOT re-run any agents

### 7.2 Approval on a Non-Existent Session (API mode)

**curl:**
```bash
curl -X POST $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "yes"}], "model": "loan-agent", "session_id": "nonexistent-session"}'
```

**Expected behavior:**
- Server returns HTTP 404: "Session 'nonexistent-session' not found"

### 7.3 Health Check

**curl:**
```bash
curl $BASE/health
```

**Expected response:**
```json
{"status": "healthy", "agent_initialized": true}
```

### 7.4 A2A Agent Card

**curl:**
```bash
curl $BASE/.well-known/agent-card.json | python3 -m json.tool
```

**Expected behavior:**
- Returns the agent's capability card with name, description, and capabilities
- Lists all 10 declared capabilities for A2A discovery

### 7.5 Models Endpoint

**curl:**
```bash
curl $BASE/v1/models
```

**Expected response:**
```json
{"object": "list", "data": [{"id": "loan-agent", "object": "model", "owned_by": "loan-agent"}]}
```

---

## 8. LLM-as-Judge Validation

The LLM-as-Judge gate runs automatically after every orchestrator response. These scenarios
test what the judge should flag.

### 8.1 Correct Trajectory (should PASS)

Any of the prompts in sections 2–5 should produce responses that pass the judge:
- `trajectory_correct: true` — tool sequence matches expected patterns
- `grounded_in_context: true` — all values traceable to agent outputs
- `response_complete: true` — includes all required information

### 8.2 What the Judge Catches

The judge is designed to catch:
- **Wrong tool order**: e.g., PricingAgent called before UnderwritingAgent
- **Hallucinated values**: e.g., interest rate in the response doesn't match `PricingAgent_output.interest_rate`
- **Missing information**: e.g., pricing summary without monthly payment or risk tier
- **Calling all 4 agents in one turn**: should stop after PricingAgent for ELIGIBLE loans

If the judge blocks a response, the user sees:
> "I apologize, but I need to verify some information before providing a response."

Check agent logs for the `LLM Judge BLOCKED` message with the judge's reasoning.
