# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared AutoRAG retrieval tools for all sub-agents.

Three targeted functions, one per retrieval use-case:

  retrieve_eligibility_rules  — UnderwritingAgent: policy rules for eligibility determination
  retrieve_industry_guidance  — UnderwritingAgent: industry risk and NAICS ineligibility
  retrieve_regulatory_guidance— LoanDecisionAgent: ECOA/Reg B adverse action requirements
  retrieve_pricing_guidance   — PricingAgent: risk tier definitions and rate benchmarks

Each function returns a plain-text string (empty string when AutoRAG is not
configured) so callers can append it to their LLM prompt or tool response.
"""

import httpx

from small_business_loan_agent import config
from small_business_loan_agent.shared_libraries.logging_config import get_logger

logger = get_logger(__name__)

_MAX_RESULTS = 3


def _search(query: str, max_results: int = _MAX_RESULTS) -> str:
    """Low-level search against the configured vector store. Returns joined text."""
    if not config.using_autorag():
        return ""

    vs_id = config.AUTORAG_VECTOR_STORE_ID
    logger.info(f"AutoRAG search (VS:{vs_id[:8]}…): {query[:80]!r}")
    try:
        resp = httpx.post(
            f"{config.AUTORAG_BASE_URL}/v1/vector_stores/{vs_id}/search",
            json={"query": query, "max_num_results": max_results},
            verify=config.AUTORAG_SSL_VERIFY,
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(f"AutoRAG search failed ({exc!r}) — continuing without RAG context")
        return ""

    chunks = resp.json().get("data", [])
    logger.info(f"AutoRAG returned {len(chunks)} chunk(s)")
    return "\n\n".join(
        c["content"][0]["text"]
        for c in chunks
        if c.get("content")
    )


def retrieve_eligibility_rules(
    industry: str,
    years_in_business: str,
    annual_revenue: str,
    loan_amount: str,
    loan_to_revenue_ratio: str = "",
) -> str:
    """Retrieve SBA eligibility rules relevant to this loan application profile.

    Used by UnderwritingAgent to ground its eligibility determination in
    actual policy text rather than relying solely on the LLM's training.

    Returns:
        Retrieved policy text, or empty string if AutoRAG is not configured.
    """
    query = (
        f"SBA 7(a) loan eligibility requirements for {industry} business "
        f"with {years_in_business} years operating history, "
        f"annual revenue {annual_revenue}, loan amount {loan_amount}"
    )
    if loan_to_revenue_ratio:
        query += f", loan-to-revenue ratio {loan_to_revenue_ratio}"
    return _search(query)


def retrieve_industry_guidance(industry: str, naics_code: str = "") -> str:
    """Retrieve industry-specific eligibility and risk guidance.

    Used by UnderwritingAgent to determine if an industry is SBA-ineligible
    (13 CFR § 120.110) or high-risk, and what additional scrutiny applies.

    Returns:
        Retrieved guidance text, or empty string if AutoRAG is not configured.
    """
    query = f"SBA eligibility ineligible industry {industry}"
    if naics_code:
        query += f" NAICS code {naics_code}"
    query += " risk tier classification prohibited business types"
    return _search(query)


def retrieve_regulatory_guidance(risk_flags: list[str], eligibility_status: str) -> str:
    """Retrieve ECOA/Regulation B adverse action requirements.

    Used by LoanDecisionAgent to ground decline letters in actual regulatory
    text — specific reason codes, required notice elements, timing rules.

    Args:
        risk_flags: List of risk flags from UnderwritingAgent output.
        eligibility_status: Should be "INELIGIBLE" for this path.

    Returns:
        Retrieved Reg B / ECOA text, or empty string if AutoRAG is not configured.
    """
    flags_str = "; ".join(risk_flags) if risk_flags else "does not meet eligibility requirements"
    query = (
        f"ECOA adverse action notice specific reasons Regulation B 12 CFR 1002.9 "
        f"decline reasons: {flags_str}"
    )
    return _search(query)


def retrieve_pricing_guidance(risk_tier: str, industry: str, loan_amount: str) -> str:
    """Retrieve risk tier and interest rate guidance.

    Used by PricingAgent to provide context-aware rate explanations grounded
    in documented tier definitions and benchmark data.

    Returns:
        Retrieved pricing guidance text, or empty string if AutoRAG is not configured.
    """
    query = (
        f"interest rate risk tier {risk_tier} small business loan {industry} "
        f"loan amount {loan_amount} SBA guarantee fee DSCR collateral"
    )
    return _search(query)
