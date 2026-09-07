#!/usr/bin/env python3
"""Seed the eligibility rules into an OGX AutoRAG vector store.

One-time operator script — not deployed with the agent.

Usage:
    AUTORAG_BASE_URL=https://autorag-ogx-autorag.apps.example.com \\
        uv run python3 tools/seed_autorag.py

After it finishes, copy the printed vector_store_id into:
    AUTORAG_VECTOR_STORE_ID=<id>

in your .env (local) or the sandbox1388 overlay configmap (on-cluster).
"""

import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import httpx

BASE_URL = os.environ.get("AUTORAG_BASE_URL", "").rstrip("/")
SSL_VERIFY = os.environ.get("AUTORAG_SSL_VERIFY", "false").lower() == "true"
RULES_PATH = Path(__file__).parent.parent / "small_business_loan_agent" / "sub_agents" / "underwriting" / "eligibility_rules.json"

ACTION_LABELS = {"ELIGIBLE": "APPROVE", "INELIGIBLE": "REJECT", "REVIEW": "FLAG FOR MANUAL REVIEW"}


def rules_to_markdown(rules: list[dict]) -> str:
    """Convert the eligibility rules list to readable markdown for better embedding quality."""
    lines = ["# Cymbal Bank — Small Business Loan Eligibility Rules\n"]
    for rule in rules:
        rid = rule["id"]
        desc = rule["description"]
        action = rule["action"]
        conds = rule.get("conditions", {})
        label = ACTION_LABELS.get(action, action)

        lines.append(f"## {rid}: {desc}")
        lines.append(f"**Decision**: {label}")
        lines.append("")
        lines.append("**Conditions**:")
        for key, val in conds.items():
            human_key = key.replace("_", " ")
            if isinstance(val, list):
                lines.append(f"- {human_key}: {', '.join(str(v) for v in val)}")
            elif isinstance(val, (int, float)) and "revenue" in key:
                lines.append(f"- {human_key}: ${val:,.0f}")
            elif isinstance(val, float) and "ratio" in key:
                lines.append(f"- {human_key}: {val * 100:.0f}%")
            else:
                lines.append(f"- {human_key}: {val}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not BASE_URL:
        print("ERROR: Set AUTORAG_BASE_URL before running this script.", file=sys.stderr)
        sys.exit(1)

    client = httpx.Client(base_url=BASE_URL, verify=SSL_VERIFY, timeout=60)

    # 1 — Health check
    print(f"Connecting to OGX at {BASE_URL} …")
    r = client.get("/v1/health")
    r.raise_for_status()
    print(f"  OGX status: {r.json().get('status')}")

    # 2 — Load and convert rules
    with open(RULES_PATH) as f:
        data = json.load(f)
    rules = data["rules"]
    markdown = rules_to_markdown(rules)
    print(f"  Converted {len(rules)} eligibility rules to markdown ({len(markdown)} chars)")

    # 3 — Upload file
    print("Uploading eligibility rules file …")
    r = client.post(
        "/v1/files",
        files={"file": ("eligibility_rules.md", BytesIO(markdown.encode()), "text/markdown")},
        data={"purpose": "assistants"},
    )
    r.raise_for_status()
    file_id = r.json()["id"]
    print(f"  file_id: {file_id}")

    # 4 — Create vector store
    # embedding_model is an OGX-specific extra field (not in OpenAI spec) — required by this OGX version
    print("Creating vector store …")
    r = client.post(
        "/v1/vector_stores",
        json={
            "name": "loan-eligibility-rules",
            "embedding_model": "sentence-transformers/nomic-ai/nomic-embed-text-v1.5",
            "metadata": {"source": "eligibility_rules.json", "agent": "small-business-loan-agent"},
        },
    )
    r.raise_for_status()
    vector_store_id = r.json()["id"]
    print(f"  vector_store_id: {vector_store_id}")

    # 5 — Add file to vector store
    print("Adding file to vector store (embedding …) …")
    r = client.post(
        f"/v1/vector_stores/{vector_store_id}/files",
        json={"file_id": file_id, "chunking_strategy": {"type": "auto"}},
    )
    r.raise_for_status()

    # 6 — Poll until ingestion completes
    for attempt in range(30):
        r = client.get(f"/v1/vector_stores/{vector_store_id}/files/{file_id}")
        r.raise_for_status()
        status = r.json().get("status")
        print(f"  ingestion status: {status} (attempt {attempt + 1})")
        if status == "completed":
            break
        if status == "failed":
            print("ERROR: Ingestion failed.", file=sys.stderr)
            sys.exit(1)
        time.sleep(3)
    else:
        print("ERROR: Timed out waiting for ingestion.", file=sys.stderr)
        sys.exit(1)

    # 7 — Smoke-test retrieval
    print("\nSmoke-testing retrieval …")
    test_queries = [
        "annual revenue loan to revenue ratio approval",
        "high risk industry cannabis gambling",
        "years in business minimum requirement",
    ]
    for query in test_queries:
        r = client.post(
            f"/v1/vector_stores/{vector_store_id}/search",
            json={"query": query, "max_num_results": 2},
        )
        r.raise_for_status()
        hits = r.json().get("data", [])
        print(f"  '{query[:50]}' → {len(hits)} hit(s)")
        for hit in hits:
            score = hit.get("score", "?")
            snippet = (hit.get("content") or [{}])[0].get("text", "")[:80].replace("\n", " ")
            print(f"    score={score:.3f}  {snippet!r}")

    print(f"\n✅  Done. Add to your config:\n\n    AUTORAG_VECTOR_STORE_ID={vector_store_id}\n")


if __name__ == "__main__":
    main()
