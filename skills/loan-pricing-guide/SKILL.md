---
name: loan-pricing-guide
description: Risk tier definitions, interest rate ranges, and guidance for presenting Cymbal Bank loan pricing clearly to applicants
---

# Cymbal Bank — Loan Pricing Guide

## Risk Tier Table

| Tier | Name | Eligibility Status | Typical Rate | Profile |
|------|------|--------------------|-------------|---------|
| Tier 1 | Low Risk | ELIGIBLE | 6.00 – 7.25% | Strong revenue (>$500K), 5+ years, low LTR |
| Tier 2 | Medium Risk | ELIGIBLE or REVIEW | 7.50 – 8.75% | Adequate revenue, 3-5 years, moderate LTR |
| Tier 3 | Elevated Risk | REVIEW | 9.00 – 11.00% | Marginal revenue, 2-3 years, higher LTR or risk flag |

The interest rate within each tier depends on:
- Loan term (longer terms carry slightly higher rates)
- Existing debt burden
- Collateral quality and coverage ratio
- Industry risk profile

---

## How to Present Pricing to the Applicant

After PricingAgent returns results, present ALL of the following clearly:

1. **Approved loan amount** (matches requested amount unless adjusted)
2. **Interest rate** — state as annual percentage rate (APR), e.g. "8.50% APR"
3. **Loan term** — in months and converted to years, e.g. "60 months (5 years)"
4. **Monthly payment** — the fixed monthly installment
5. **Total interest paid** — total cost of borrowing over the full term
6. **Risk tier** — explain what it means in plain language

**Example presentation:**
> Cymbal Bank is prepared to offer Sunrise Bakehouse LLC a loan of **$180,000** at
> **7.25% APR** over **60 months (5 years)**. Monthly payments would be **$3,569.21**,
> with total interest of **$34,152.60**. This qualifies as a **Tier 1 (Low Risk)** loan
> based on the business's strong revenue history and low loan-to-revenue ratio.

---

## Explaining Elevated Rates

If the applicant asks why the rate is higher than expected:
- Reference the risk tier and the specific factors (operating history, debt burden, LTR)
- Explain that a stronger track record or lower loan amount could improve the tier
- Do NOT promise rate reductions — present the offered rate as final

---

## Approval Prompt

After presenting pricing, always ask:
> "Do you approve this loan for **[Business Name]**? (yes/no)"

Wait for explicit user confirmation before proceeding to LoanDecisionAgent.
