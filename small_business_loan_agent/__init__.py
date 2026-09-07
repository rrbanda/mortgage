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

"""Small Business Loan Processing Agent — ADK reference implementation."""

import os
import sys

# Ensure the parent directory is on sys.path so the package is importable
# (required for `adk eval` which doesn't set up sys.path like `adk web` does)
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Only attempt GCP auth when Vertex AI is the active backend.
# When MAAS_BASE_URL or GOOGLE_API_KEY are set, GCP credentials are not needed.
from small_business_loan_agent.config import MAAS_BASE_URL, MAAS_API_KEY, GOOGLE_CLOUD_LOCATION  # noqa: E402

_using_maas = bool(MAAS_BASE_URL and MAAS_API_KEY)
_using_api_key = bool(os.getenv("GOOGLE_API_KEY"))

if not _using_maas and not _using_api_key:
    try:
        import google.auth
        _, project_id = google.auth.default()
        if project_id:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", GOOGLE_CLOUD_LOCATION)
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    except Exception:
        pass  # No GCP credentials — that's fine when using MaaS or API key

from small_business_loan_agent import agent  # noqa: F401, E402
