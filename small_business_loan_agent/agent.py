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

"""
ADK Agent for small business loan processing.

Orchestrator-based agent architecture with 4 specialized sub-agents:
  1. DocumentExtractionAgent - Extracts data from loan application documents
  2. UnderwritingAgent - Validates data and checks eligibility
  3. PricingAgent - Calculates interest rate and terms
  4. LoanDecisionAgent - Finalizes decision after human approval
"""

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools.agent_tool import AgentTool

from small_business_loan_agent.callbacks import (
    before_tool_callback_check_process_status,
    extract_request_id_from_request,
    llm_judge_gate,
)
from small_business_loan_agent.config import DEFAULT_MODEL_NAME
from small_business_loan_agent.gemini_custom import get_model
from small_business_loan_agent.prompt import ORCHESTRATOR_PROMPT
from small_business_loan_agent.sub_agents.document_extraction import (
    document_extraction_agent,
)
from small_business_loan_agent.sub_agents.loan_decision import loan_decision_agent
from small_business_loan_agent.sub_agents.pricing import pricing_agent
from small_business_loan_agent.sub_agents.underwriting import underwriting_agent
from small_business_loan_agent.tools.tools import check_process_status

# --- Constants ---
MODEL_NAME = DEFAULT_MODEL_NAME

# --- Root Orchestrator Agent ---
root_agent = LlmAgent(
    name="SmallBusinessLoanOrchestratorAgent",
    model=get_model(MODEL_NAME),
    instruction=ORCHESTRATOR_PROMPT,
    description="Orchestrates small business loan processing by coordinating sub-agents, handling user approval, and managing the complete application workflow",
    before_agent_callback=extract_request_id_from_request,
    before_tool_callback=before_tool_callback_check_process_status,
    after_agent_callback=llm_judge_gate,
    tools=[
        check_process_status,
        AgentTool(document_extraction_agent),
        AgentTool(underwriting_agent),
        AgentTool(pricing_agent),
        AgentTool(loan_decision_agent),
    ],
)


# --- App for ADK Web (local development) ---
app = App(
    name="small_business_loan_agent",
    root_agent=root_agent,
)
