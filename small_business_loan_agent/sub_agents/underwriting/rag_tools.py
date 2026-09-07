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

"""RAG retrieval entry points for the Underwriting Agent.

Delegates to the shared rag_tools library and combines two targeted
queries — eligibility policy and industry guidance — into a single
structured context block the UnderwritingAgent LLM can consume.
"""

from small_business_loan_agent.shared_libraries.logging_config import get_logger
from small_business_loan_agent.shared_libraries.rag_tools import (
    retrieve_eligibility_rules,
    retrieve_industry_guidance,
)

logger = get_logger(__name__)


def retrieve_underwriting_context(
    industry: str,
    years_in_business: str,
    annual_revenue: str,
    loan_amount: str,
    loan_to_revenue_ratio: str = "",
    naics_code: str = "",
) -> str:
    """Retrieve all AutoRAG context needed for underwriting a loan application.

    Executes two targeted searches:
      1. SBA eligibility rules matching this application profile
      2. Industry-specific risk and ineligibility guidance

    Returns a combined context block ready to append to the underwriting prompt.
    Empty string when AutoRAG is not configured (caller uses static rules).
    """
    eligibility_text = retrieve_eligibility_rules(
        industry=industry,
        years_in_business=years_in_business,
        annual_revenue=annual_revenue,
        loan_amount=loan_amount,
        loan_to_revenue_ratio=loan_to_revenue_ratio,
    )

    industry_text = retrieve_industry_guidance(
        industry=industry,
        naics_code=naics_code,
    )

    if not eligibility_text and not industry_text:
        logger.info("AutoRAG not configured — using static eligibility rules from session state")
        return ""

    parts = []
    if eligibility_text:
        parts.append("## Eligibility Policy Rules (AutoRAG)\n\n" + eligibility_text)
    if industry_text:
        parts.append("## Industry Risk Guidance (AutoRAG)\n\n" + industry_text)

    combined = "\n\n---\n\n".join(parts)
    logger.info(f"AutoRAG underwriting context: {len(combined)} chars from {len(parts)} retrieval(s)")
    return combined
