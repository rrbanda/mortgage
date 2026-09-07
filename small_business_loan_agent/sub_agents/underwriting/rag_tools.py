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

"""RAG retrieval tools for the Underwriting Agent.

Uses the AutoRAG OGX vector store to retrieve eligibility rules relevant
to a specific loan application, replacing static JSON file lookup when
AUTORAG_BASE_URL and AUTORAG_VECTOR_STORE_ID are configured.
"""

import httpx

from small_business_loan_agent import config


def retrieve_eligibility_rules(query: str) -> str:
    """Search the eligibility rule knowledge base for rules relevant to this loan application.

    Args:
        query: A natural-language description of the loan scenario — include key
               facts such as annual revenue, years in business, loan amount,
               loan-to-revenue ratio, and industry. The more context, the better
               the retrieval quality.

    Returns:
        Retrieved policy rules as plain text, or an empty string if AutoRAG is
        not configured (caller falls back to the static rules already in session state).
    """
    if not config.using_autorag():
        return ""

    resp = httpx.post(
        f"{config.AUTORAG_BASE_URL}/v1/vector_stores/{config.AUTORAG_VECTOR_STORE_ID}/search",
        json={"query": query, "max_num_results": 5},
        verify=config.AUTORAG_SSL_VERIFY,
        timeout=30,
    )
    resp.raise_for_status()
    chunks = resp.json().get("data", [])
    return "\n\n".join(
        c["content"][0]["text"]
        for c in chunks
        if c.get("content")
    )
