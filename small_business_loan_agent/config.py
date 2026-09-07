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
Central configuration for the Small Business Loan Agent.

All env-var reads live here. Every other module imports from this file
instead of calling os.getenv() directly.

Section A: Env-var backed settings (operators control via .env)
Section B: Code constants (shared across modules, not user-configurable)
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Section A — Infrastructure / runtime settings
# ---------------------------------------------------------------------------

# Model
DEFAULT_MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")

# MaaS (OpenAI-compatible endpoint)
MAAS_BASE_URL: str = os.getenv("MAAS_BASE_URL", "").rstrip("/")
MAAS_API_KEY: str = os.getenv("MAAS_API_KEY", "")
# Path template — {model} is replaced with the model name at call time.
# Override if your MaaS proxy uses a different routing convention.
MAAS_URL_PATH: str = os.getenv("MAAS_URL_PATH", "/gemini-external/{model}/v1")
# Set to "true" to enable SSL verification (e.g. production endpoint with valid cert)
MAAS_SSL_VERIFY: bool = os.getenv("MAAS_SSL_VERIFY", "false").lower() == "true"

# GCP / Vertex AI
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

# SQLite state storage
STATE_DB_PATH: str = os.getenv("STATE_DB_PATH", "./small_business_loan_agent.db")

# ---------------------------------------------------------------------------
# Section A — Business rules (adjustable per deployment / product)
# ---------------------------------------------------------------------------

# Branding
BANK_NAME: str = os.getenv("BANK_NAME", "Cymbal Bank")

# Loan request ID format — prefix and regex width digits are configurable
# so the system can be adapted without touching Python source.
LOAN_ID_PREFIX: str = os.getenv("LOAN_ID_PREFIX", "SBL")

# Interest rates per risk tier (percentage, e.g. 6.50 = 6.50%)
RATE_TIER_1: float = float(os.getenv("RATE_TIER_1", "6.50"))   # Low Risk
RATE_TIER_2: float = float(os.getenv("RATE_TIER_2", "7.75"))   # Moderate Risk
RATE_TIER_3: float = float(os.getenv("RATE_TIER_3", "9.25"))   # Elevated Risk
RATE_TIER_4: float = float(os.getenv("RATE_TIER_4", "11.00"))  # High Risk

# Loan term default when not specified in application (months)
DEFAULT_LOAN_TERM_MONTHS: int = int(os.getenv("DEFAULT_LOAN_TERM_MONTHS", "60"))

# Compliance window for post-approval insurance verification (days)
INSURANCE_VERIFICATION_DAYS: int = int(os.getenv("INSURANCE_VERIFICATION_DAYS", "30"))

# Path to the JSON eligibility rules file used by UnderwritingAgent
ELIGIBILITY_RULES_PATH: str = os.getenv(
    "ELIGIBILITY_RULES_PATH",
    str(Path(__file__).parent / "sub_agents" / "underwriting" / "eligibility_rules.json"),
)

# ---------------------------------------------------------------------------
# Section B — Code constants (shared magic strings; not user-configurable)
# ---------------------------------------------------------------------------

# Agent output state keys — referenced by orchestrator tools, state callbacks,
# and the LLM judge. Must match the output_key= set on each sub-agent.
OUTPUT_KEY_DOCUMENT = "DocumentExtractionAgent_output"
OUTPUT_KEY_UNDERWRITING = "UnderwritingAgent_output"
OUTPUT_KEY_PRICING = "PricingAgent_output"
OUTPUT_KEY_LOAN_DECISION = "LoanDecisionAgent_output"

# Ordered map from agent name → state key (used for resume loading)
AGENT_OUTPUT_KEY_MAP: dict[str, str] = {
    "DocumentExtractionAgent": OUTPUT_KEY_DOCUMENT,
    "UnderwritingAgent": OUTPUT_KEY_UNDERWRITING,
    "PricingAgent": OUTPUT_KEY_PRICING,
    "LoanDecisionAgent": OUTPUT_KEY_LOAN_DECISION,
}

# Loan request ID regex — year (4 digits) + sequence (5 digits)
LOAN_ID_REGEX: str = rf"{LOAN_ID_PREFIX}-\d{{4}}-\d{{5}}"


# ---------------------------------------------------------------------------
# Section B — Helpers
# ---------------------------------------------------------------------------

def _maas_base() -> str:
    """Return the current MaaS base URL (re-reads os.environ so dotenv works regardless of import order)."""
    return (os.getenv("MAAS_BASE_URL") or MAAS_BASE_URL).rstrip("/")


def _maas_key() -> str:
    """Return the current MaaS API key (re-reads os.environ)."""
    return os.getenv("MAAS_API_KEY") or MAAS_API_KEY


def maas_api_base(model_name: str) -> str:
    """Build the per-model MaaS API base URL from the configured template."""
    path = os.getenv("MAAS_URL_PATH") or MAAS_URL_PATH
    return _maas_base() + path.format(model=model_name)


def using_maas() -> bool:
    """Return True when MaaS is the active model backend."""
    return bool(_maas_base() and _maas_key())


# ---------------------------------------------------------------------------
# Section A — AutoRAG / OGX vector store (eligibility rule retrieval)
# ---------------------------------------------------------------------------

# Base URL of the OGX server (AutoRAG) — e.g. https://autorag-ogx-autorag.apps.example.com
AUTORAG_BASE_URL: str = os.getenv("AUTORAG_BASE_URL", "").rstrip("/")

# Vector store ID created by tools/seed_autorag.py
AUTORAG_VECTOR_STORE_ID: str = os.getenv("AUTORAG_VECTOR_STORE_ID", "")

# Set to "true" only when OGX has a CA-signed TLS cert
AUTORAG_SSL_VERIFY: bool = os.getenv("AUTORAG_SSL_VERIFY", "false").lower() == "true"


def using_autorag() -> bool:
    """Return True when the AutoRAG vector store is configured."""
    return bool(AUTORAG_BASE_URL and AUTORAG_VECTOR_STORE_ID)
