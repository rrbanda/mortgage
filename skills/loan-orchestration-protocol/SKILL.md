---
name: loan-orchestration-protocol
description: Step-by-step HITL workflow for processing a Cymbal Bank small business loan application, including the INELIGIBLE short-circuit and repair-and-resume logic
allowed-tools: check_process_status DocumentExtractionAgent UnderwritingAgent PricingAgent LoanDecisionAgent
metadata:
  adk_inject_state: true
---

# Cymbal Bank — Loan Processing Workflow Protocol

Use this protocol for every new loan application request.

## Step 0 — Always call check_process_status first

Before doing anything else, call `check_process_status` with the loan request ID.

- If the process is **new**: start from Step 1.
- If the process is **resuming** (a prior run completed some steps): skip completed steps and continue from where you left off. The tool will tell you exactly which step to jump to.
- If the process is **pending_approval**: wait for the user to say yes/no.
- If the process is **completed**: report the final decision — do not re-run any agents.

## Step 1 — Document Extraction

Call `DocumentExtractionAgent` with the full user-provided application text.

It returns structured fields: `business_name`, `owner_name`, `loan_amount_requested`,
`annual_revenue`, `years_in_business`, `employees`, `industry`, `collateral`, and more.

If required fields are missing: tell the user exactly which fields are missing and ask them
to provide the missing information. Do NOT proceed to underwriting with incomplete data.

## Step 2 — Underwriting

Call `UnderwritingAgent`. It validates the extracted data against internal records and
checks eligibility against bank policy rules.

It returns:
- `eligibility_status`: one of `ELIGIBLE`, `REVIEW`, or `INELIGIBLE`
- `risk_flags`: list of policy violations or concerns
- `matched_rule`: the policy rule that determined the outcome

**INELIGIBLE path (short-circuit):**
If `eligibility_status == "INELIGIBLE"`, skip Step 3 entirely. Go directly to Step 4
(LoanDecisionAgent) to generate the decline letter. Do NOT call PricingAgent.

**ELIGIBLE or REVIEW path:**
Continue to Step 3.

## Step 3 — Pricing (ELIGIBLE/REVIEW only)

Call `PricingAgent`. It calculates the interest rate, monthly payment, and total cost.

After pricing completes, STOP and present the results to the user:
- Business name and loan amount
- Eligibility status and risk tier
- Interest rate and monthly payment
- Ask: "Do you approve this loan? (yes/no)"

Then WAIT. Do not call LoanDecisionAgent until the user explicitly says "yes".

If the user says "no": acknowledge and close the application.

## Step 4 — Loan Decision

Call `LoanDecisionAgent` only when:
- The user has said "yes" (approved path), OR
- The loan is INELIGIBLE (decline path, no approval needed)

It generates the official decision letter with a reference ID.

## Step 5 — Present the Final Decision

Present the decision letter to the user. The letter must be professional and complete —
approval or decline.

---

## Current Application Context

Request ID: {loan_request_id?}
