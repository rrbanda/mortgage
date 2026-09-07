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
Model factory for the loan agent.

Supports two backends selected by environment variables:
  - MaaS (OpenAI-compatible):  set MAAS_BASE_URL + MAAS_API_KEY
  - Gemini API / Vertex AI:    set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT

MaaS integration is provided by the rh-maas-litellm package.
All configuration is read from small_business_loan_agent.config.
"""

import os
from functools import cached_property

from google.adk.models import Gemini
from google.genai import Client, types

# rh-maas-litellm upstream package handles MaaS-specific ADK integration
from rh_maas_litellm import MaaSConfig, MaaSLiteLlm, bootstrap, get_maas_model

from small_business_loan_agent import config

# Apply litellm patches once at import time (SSL + PDF MIME routing)
bootstrap(ssl_verify=config.MAAS_SSL_VERIFY)

# MaaS returns gzip+chunked which triggers an httpcore read-stall bug.
# Force identity encoding so the response body is read without decompression.
import litellm
_orig_headers: dict = litellm.headers or {}
litellm.headers = {**_orig_headers, "Accept-Encoding": "identity"}


# ---------------------------------------------------------------------------
# GeminiPreview — native Gemini API / Vertex AI path (not part of rh-maas-litellm)
# ---------------------------------------------------------------------------
class GeminiPreview(Gemini):
    @cached_property
    def api_client(self) -> Client:
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            return Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    headers=self._tracking_headers(),
                    retry_options=self.retry_options,
                ),
            )
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        return Client(
            project=project,
            location=config.GOOGLE_CLOUD_LOCATION,
            http_options=types.HttpOptions(
                headers=self._tracking_headers(),
                retry_options=self.retry_options,
            ),
        )


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------
def get_model(model_name: str = config.DEFAULT_MODEL_NAME) -> MaaSLiteLlm | GeminiPreview:
    """Return the appropriate model backend based on environment variables."""
    if config.using_maas():
        return get_maas_model(
            model_name,
            MaaSConfig(
                base_url=config._maas_base(),
                api_key=config._maas_key(),
                url_path=os.getenv("MAAS_URL_PATH", "/gemini-external/{model}/v1"),
                ssl_verify=config.MAAS_SSL_VERIFY,
            ),
        )
    return GeminiPreview(model=model_name)
