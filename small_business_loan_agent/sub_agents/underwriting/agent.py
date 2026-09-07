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

"""Underwriting Agent definition."""

import os

from google.adk.agents import LlmAgent

from small_business_loan_agent.config import DEFAULT_MODEL_NAME
from small_business_loan_agent.gemini_custom import get_model
from small_business_loan_agent.shared_libraries.state_utils.state_callbacks import (
    after_agent_callback_with_state_logging,
    before_agent_callback_with_state_check,
)
from small_business_loan_agent.sub_agents.underwriting.models import UnderwritingReport
from small_business_loan_agent.sub_agents.underwriting.prompt import UNDERWRITING_PROMPT
from small_business_loan_agent.sub_agents.underwriting.rag_tools import (
    retrieve_eligibility_rules,
)
from small_business_loan_agent.sub_agents.underwriting.tools import (
    get_internal_business_data,
)

MODEL_NAME = DEFAULT_MODEL_NAME

underwriting_agent = LlmAgent(
    name="UnderwritingAgent",
    model=get_model(MODEL_NAME),
    instruction=UNDERWRITING_PROMPT,
    description="Validates application data against internal records and checks business eligibility",
    before_agent_callback=before_agent_callback_with_state_check,
    tools=[get_internal_business_data, retrieve_eligibility_rules],
    after_agent_callback=after_agent_callback_with_state_logging,
    output_schema=UnderwritingReport,
    output_key="UnderwritingAgent_output",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
