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

"""Document Extraction Agent definition."""

import os

from google.adk.agents import LlmAgent

from small_business_loan_agent.config import DEFAULT_MODEL_NAME
from small_business_loan_agent.gemini_custom import get_model
from small_business_loan_agent.shared_libraries.state_utils.state_callbacks import (
    after_agent_callback_with_state_logging,
    before_agent_callback_with_state_check,
)
from small_business_loan_agent.sub_agents.document_extraction.models import (
    LoanApplicationData,
)
from small_business_loan_agent.sub_agents.document_extraction.prompt import (
    DOCUMENT_EXTRACTION_PROMPT,
)
from small_business_loan_agent.sub_agents.document_extraction.tools import (
    inject_document_into_request,
)

MODEL_NAME = DEFAULT_MODEL_NAME

document_extraction_agent = LlmAgent(
    name="DocumentExtractionAgent",
    model=get_model(MODEL_NAME),
    instruction=DOCUMENT_EXTRACTION_PROMPT,
    description="Extracts structured loan application data from uploaded documents using Gemini's multimodal capabilities",
    before_agent_callback=[before_agent_callback_with_state_check],
    before_model_callback=inject_document_into_request,
    after_agent_callback=[after_agent_callback_with_state_logging],
    output_schema=LoanApplicationData,
    output_key="DocumentExtractionAgent_output",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
