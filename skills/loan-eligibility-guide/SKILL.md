---
name: loan-eligibility-guide
description: Eligibility criteria, risk flags, and INELIGIBLE/REVIEW/ELIGIBLE decision guide for Cymbal Bank small business loans — use this to explain underwriting decisions to applicants
---

# Cymbal Bank — Loan Eligibility Guide

## The 5 Eligibility Rules

### Rule 1 — Approve (ELIGIBLE)
**Conditions:** Annual revenue > $500K AND business has 3+ years of operations AND
loan-to-revenue ratio ≤ 50%.

All three conditions must be met for an ELIGIBLE outcome.

### Rule 2 — Flag for Review (REVIEW)
**Conditions:** Annual revenue between $200K and $500K AND business has 2+ years.

These applications are eligible for consideration but require additional scrutiny.
They typically receive a higher interest rate (Tier 2 or Tier 3).

### Rule 3 — Reject (INELIGIBLE)
**Condition:** Business has been operating for less than 1 year.

Businesses under 12 months old do not have sufficient operating history.
The applicant should reapply after reaching 1 year of operations.

### Rule 4 — Reject (INELIGIBLE)
**Condition:** Loan-to-revenue ratio exceeds 75%.

If the requested loan amount is more than 75% of annual revenue, the debt burden
is considered unsustainable. Example: $250K loan on $85K revenue = 294% ratio → INELIGIBLE.

### Rule 5 — Flag for Review (REVIEW)
**Conditions:** Industry is in a high-risk category: Cannabis, Cryptocurrency, or Gambling.

These industries face regulatory uncertainty and require manual underwriting review.

---

## What Each Status Means

| Status | Meaning | Next Step |
|--------|---------|-----------|
| **ELIGIBLE** | Meets all approval criteria | Proceed to pricing; present to user for approval |
| **REVIEW** | Marginal — meets some criteria | Proceed to pricing at higher tier; present to user |
| **INELIGIBLE** | Fails one or more hard rules | Generate decline letter immediately; no pricing |

---

## Common Risk Flags (reported by UnderwritingAgent)

- `"Business in operation for less than 1 year"` — Rule 3 violation
- `"Loan-to-revenue ratio (X%) exceeds policy threshold of 75%"` — Rule 4 violation
- `"Major discrepancies between application data and internal records"` — data integrity concern
- `"No collateral offered"` — increases risk tier, may not be disqualifying alone
- `"Existing debt burden high"` — existing debt reduces repayment capacity

---

## Explaining a Decision to an Applicant

**For ELIGIBLE/REVIEW:** Explain that the application has been reviewed and pricing has
been calculated. Be specific about the rate and term.

**For INELIGIBLE:** Be professional and specific. Reference the exact rule violated.
Never use technical jargon. Invite the applicant to reapply when circumstances change.
See the `loan-adverse-action` skill for regulatory guidance on decline letters.
