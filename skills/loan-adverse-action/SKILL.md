---
name: loan-adverse-action
description: Regulatory guidance for generating ECOA-compliant adverse action decline letters for denied Cymbal Bank loan applications
metadata:
  adk_inject_state: true
---

# Cymbal Bank — Adverse Action Notice Guide

## Regulatory Background

Under the **Equal Credit Opportunity Act (ECOA)** and **Regulation B**, when a lender
denies credit, it must provide the applicant with:

1. A **notice of adverse action** (the decline letter)
2. **Specific reasons** for the denial — vague statements ("credit was unsatisfactory")
   are not permitted; the reasons must be specific and related to the actual decision factors
3. Contact information so the applicant can request additional information if desired

The **Fair Credit Reporting Act (FCRA)** also applies if consumer credit reports were used
(not applicable for this internal business credit review, but note for future reference).

---

## Required Elements in a Decline Letter

Every decline letter MUST include all of the following:

1. **Applicant name and business name** — addressed personally
2. **Statement of denial** — clear and unambiguous ("we are unable to approve…")
3. **Specific decline reasons** — from the underwriting risk flags, stated in plain English
4. **Decision letter reference ID** — e.g., `DL-2025-00205-001`
5. **Invitation to reapply** — when circumstances change; do not discourage future applications
6. **Professional closing** — signed from Cymbal Bank

---

## Writing the Decline Reasons

Use the underwriting `risk_flags` directly, translated to plain English:

| Risk Flag | Plain English Reason |
|-----------|---------------------|
| Business operating < 1 year | "Business has not yet established a 1-year operating history as required by our lending policy." |
| LTR exceeds 75% | "The requested loan amount represents a debt-to-revenue ratio that exceeds our maximum policy threshold." |
| Data discrepancies | "Significant discrepancies were identified between the application data and our business records." |
| No collateral | "Insufficient collateral was offered to secure the requested loan amount." |

Cite 2-3 specific reasons. Do not cite more than 5 (too many reasons can appear punitive).

---

## Letter Tone and Language

- **Professional and respectful** — the applicant is a business owner, not a bad actor
- **Specific but not technical** — say "loan-to-revenue ratio" not "LTR metric"
- **Forward-looking** — close with a genuine invitation to reapply
- **Concise** — 4-6 short paragraphs maximum

---

## Template Structure

```
Dear [Owner Name],

We regret to inform you that your loan application ([Request ID]) for
[Business Name] has been declined after careful review.

This decision was made due to the following reasons:
- [Reason 1]
- [Reason 2]
- [Reason 3 if applicable]

Your decision letter reference ID is [Letter Reference ID].

We encourage you to reapply in the future when [specific circumstance that could change].
Cymbal Bank values your business and hopes to work with you when your circumstances improve.

Sincerely,
Cymbal Bank — Commercial Lending Division
```

---

## Current Application Context

Request ID: {loan_request_id?}
