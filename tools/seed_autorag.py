#!/usr/bin/env python3
"""Seed the loan knowledge base into an OGX AutoRAG vector store.

Reads all .md files from tools/corpus/** and uploads each as a separate
document so OGX's auto-chunker produces independent, semantically
searchable vectors.

Usage:
    AUTORAG_BASE_URL=http://autorag-ogx-service.autorag.svc.cluster.local:8321 \
        uv run python3 tools/seed_autorag.py

After it finishes, copy the printed vector_store_id into:
    AUTORAG_VECTOR_STORE_ID=<id>

in the sandbox1388 overlay configmap (on-cluster) or .env (local).

Corpus layout:
    tools/corpus/
        eligibility/    — SBA eligibility rules, CFR ineligible businesses, collateral
        regulatory/     — ECOA/Regulation B adverse action requirements
        industry/       — NAICS risk classifications, industry risk guide
        pricing/        — Risk tier definitions, rate benchmarks
        faq/            — Applicant FAQ, reapplication guidance
"""

import os
import sys
import time
from io import BytesIO
from pathlib import Path

import httpx

BASE_URL = os.environ.get("AUTORAG_BASE_URL", "").rstrip("/")
SSL_VERIFY = os.environ.get("AUTORAG_SSL_VERIFY", "false").lower() == "true"
CORPUS_DIR = Path(__file__).parent / "corpus"

EMBEDDING_MODEL = "sentence-transformers/nomic-ai/nomic-embed-text-v1.5"
VECTOR_STORE_NAME = "loan-knowledge-base"


def upload_and_ingest(client: httpx.Client, vector_store_id: str, path: Path, label: str) -> str:
    """Upload one document and wait for ingestion. Returns the file_id."""
    content = path.read_bytes()

    r = client.post(
        "/v1/files",
        files={"file": (path.name, BytesIO(content), "text/markdown")},
        data={"purpose": "assistants"},
    )
    r.raise_for_status()
    file_id = r.json()["id"]

    r = client.post(
        f"/v1/vector_stores/{vector_store_id}/files",
        json={"file_id": file_id, "chunking_strategy": {"type": "auto"}},
    )
    r.raise_for_status()

    for attempt in range(40):
        r = client.get(f"/v1/vector_stores/{vector_store_id}/files/{file_id}")
        r.raise_for_status()
        status = r.json().get("status")
        if status == "completed":
            print(f"  ✓ {label} (attempt {attempt + 1})")
            return file_id
        if status == "failed":
            print(f"  ✗ FAILED: {label}", file=sys.stderr)
            sys.exit(1)
        time.sleep(3)

    print(f"  ✗ TIMEOUT: {label}", file=sys.stderr)
    sys.exit(1)


def smoke_test(client: httpx.Client, vector_store_id: str) -> None:
    queries = [
        ("eligibility", "annual revenue loan to revenue ratio years in business minimum requirement"),
        ("industry",    "cannabis marijuana gambling ineligible industry SBA"),
        ("collateral",  "collateral LTV loan to value ratio accounts receivable equipment"),
        ("regulatory",  "ECOA adverse action notice specific reasons 30 days Regulation B"),
        ("pricing",     "interest rate risk tier Tier 3 elevated risk DSCR debt service"),
        ("faq",         "how to reapply after loan decline improve application"),
    ]
    print("\nSmoke-testing retrieval …")
    for label, query in queries:
        r = client.post(
            f"/v1/vector_stores/{vector_store_id}/search",
            json={"query": query, "max_num_results": 2},
        )
        r.raise_for_status()
        hits = r.json().get("data", [])
        if hits:
            score = hits[0].get("score", 0)
            snippet = (hits[0].get("content") or [{}])[0].get("text", "")[:80].replace("\n", " ")
            print(f"  [{label}] score={score:.3f}  {snippet!r}")
        else:
            print(f"  [{label}] no hits — check corpus files")


def main() -> None:
    if not BASE_URL:
        print("ERROR: Set AUTORAG_BASE_URL before running this script.", file=sys.stderr)
        sys.exit(1)

    if not CORPUS_DIR.exists():
        print(f"ERROR: Corpus directory not found: {CORPUS_DIR}", file=sys.stderr)
        sys.exit(1)

    corpus_files = sorted(CORPUS_DIR.rglob("*.md"))
    if not corpus_files:
        print(f"ERROR: No .md files found under {CORPUS_DIR}", file=sys.stderr)
        sys.exit(1)

    client = httpx.Client(base_url=BASE_URL, verify=SSL_VERIFY, timeout=60)

    # Health check
    print(f"Connecting to OGX at {BASE_URL} …")
    r = client.get("/v1/health")
    r.raise_for_status()
    print(f"  OGX status: {r.json().get('status')}")

    # Summarise corpus
    by_domain: dict[str, list[Path]] = {}
    for f in corpus_files:
        domain = f.parent.name
        by_domain.setdefault(domain, []).append(f)
    print(f"\nCorpus: {len(corpus_files)} documents across {len(by_domain)} domains")
    for domain, files in sorted(by_domain.items()):
        total_kb = sum(f.stat().st_size for f in files) / 1024
        print(f"  {domain:15s} {len(files):3d} files  {total_kb:.1f} KB")

    # Create vector store
    print(f"\nCreating vector store '{VECTOR_STORE_NAME}' …")
    r = client.post(
        "/v1/vector_stores",
        json={
            "name": VECTOR_STORE_NAME,
            "embedding_model": EMBEDDING_MODEL,
            "metadata": {
                "source": "tools/corpus",
                "agent": "small-business-loan-agent",
                "version": "2.0",
                "domains": ",".join(sorted(by_domain.keys())),
            },
        },
    )
    r.raise_for_status()
    vector_store_id = r.json()["id"]
    print(f"  vector_store_id: {vector_store_id}")

    # Upload each file
    print("\nUploading corpus documents …")
    for domain, files in sorted(by_domain.items()):
        print(f"  [{domain}]")
        for path in sorted(files):
            label = f"{domain}/{path.name}"
            upload_and_ingest(client, vector_store_id, path, label)

    smoke_test(client, vector_store_id)

    print(f"\n✅  Done. Update your config:\n\n    AUTORAG_VECTOR_STORE_ID={vector_store_id}\n")
    print("On-cluster: edit the sandbox1388 overlay configmap or sandbox.yaml")
    print("Local:      set AUTORAG_VECTOR_STORE_ID in .env")


if __name__ == "__main__":
    main()
