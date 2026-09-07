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

"""Tools for the Loan Decision Agent — mock decision finalization."""

from google.adk.tools.tool_context import ToolContext
from small_business_loan_agent import config
from small_business_loan_agent.shared_libraries.logging_config import get_logger

logger = get_logger(__name__)


def finalize_loan_decision(tool_context: ToolContext) -> dict:
    """
    Finalize the loan decision and generate a decision letter reference.

    Handles both approval (ELIGIBLE/REVIEW) and decline (INELIGIBLE) paths.
    In production this would record in the loan origination system and trigger
    generation of official letters.
    """
    try:
        loan_request_id = tool_context.state.get("loan_request_id")
        application_data = tool_context.state.get("DocumentExtractionAgent_output") or {}
        underwriting_data = tool_context.state.get("UnderwritingAgent_output") or {}
        pricing_data = tool_context.state.get("PricingAgent_output")

        if not loan_request_id:
            return {"status": "error", "message": "loan_request_id not found in session state"}

        logger.info(f"Finalizing loan decision for: {loan_request_id}")

        # Normalise: ADK may store output_schema results as Pydantic objects or dicts
        if hasattr(application_data, "model_dump"):
            application_data = application_data.model_dump()
        if hasattr(underwriting_data, "model_dump"):
            underwriting_data = underwriting_data.model_dump()
        if hasattr(pricing_data, "model_dump"):
            pricing_data = pricing_data.model_dump()

        decision_letter_id = f"DL-{loan_request_id.replace(f'{config.LOAN_ID_PREFIX}-', '')}-001"
        business_name = application_data.get("business_name", "Applicant")
        owner_name = application_data.get("owner_name", "N/A")
        loan_amount = application_data.get("loan_amount_requested", "N/A")
        loan_term = application_data.get("loan_term_months", "N/A")
        eligibility_status = underwriting_data.get("eligibility_status", "UNKNOWN")

        # ── Decline path ────────────────────────────────────────────────────
        if eligibility_status == "INELIGIBLE":
            risk_flags = underwriting_data.get("risk_flags") or []
            matched_rule = underwriting_data.get("matched_rule") or ""
            decline_reasons = risk_flags if risk_flags else (
                [matched_rule] if matched_rule else ["Business did not meet eligibility requirements"]
            )
            return {
                "status": "success",
                "decision": "DENIED",
                "decision_letter_id": decision_letter_id,
                "business_name": business_name,
                "owner_name": owner_name,
                "loan_amount_requested": loan_amount,
                "decline_reasons": decline_reasons,
                "message": (
                    f"Loan application {loan_request_id} for {business_name} has been DENIED. "
                    f"Decision letter {decision_letter_id} has been issued. "
                    f"Decline reason(s): {'; '.join(str(r) for r in decline_reasons)}."
                ),
            }

        # ── Approval path ────────────────────────────────────────────────────
        if not pricing_data:
            return {"status": "error", "message": "Pricing data not found in session state"}

        approved_rate = pricing_data.get("interest_rate", "N/A")
        return {
            "status": "success",
            "decision": "APPROVED",
            "decision_letter_id": decision_letter_id,
            "approved_amount": loan_amount,
            "approved_rate": approved_rate,
            "approved_term": f"{loan_term} months" if loan_term != "N/A" else "N/A",
            "conditions": [
                f"Business insurance verification required within {config.INSURANCE_VERIFICATION_DAYS} days",
                "Collateral documentation to be submitted before disbursement",
            ],
            "message": (
                f"Loan {loan_request_id} for {business_name} has been APPROVED. "
                f"Decision letter {decision_letter_id} has been generated. "
                f"Approved for {loan_amount} at {approved_rate} for {loan_term} months."
            ),
        }

    except Exception as e:
        logger.error(f"Error finalizing loan decision: {e}")
        return {"status": "error", "message": f"Error: {e!s}"}
