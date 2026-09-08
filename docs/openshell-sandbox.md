# OpenShell Sandbox Deployment

Run the Small Business Loan Agent inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) sandbox with policy-enforced network isolation and credential injection. This is the recommended deployment mode for production environments where the agent processes real loan applications with sensitive financial data.

## Why Use a Sandbox?

The loan agent connects to external systems that handle sensitive financial and regulatory data:

| System | Risk | Sandbox Benefit |
|--------|------|-----------------|
| MaaS Gateway (LLM) | Sends loan application data to LLM for processing | Egress policy limits to specific MaaS endpoint |
| AutoRAG / OGX (RAG) | Queries regulatory knowledge base with application details | Egress policy limits to AutoRAG endpoint |
| SQLite (local) | Stores all application data and workflow state | No network exposure; file-level isolation |

Without a sandbox, a compromised agent (via prompt injection or supply chain attack) could exfiltrate PII (business owner names, EINs, financial data) to arbitrary endpoints. The OpenShell L7 policy engine blocks all traffic not matching the egress rules.

## Prerequisites

- OpenShift cluster with [OpenShell gateway](https://github.com/NVIDIA/OpenShell) installed
- ArgoCD for GitOps deployment (recommended)
- Podman or Docker for image builds
- `oc` CLI authenticated to the cluster

## Step 1: Build the Sandbox Image

The `Containerfile` already includes OpenShell dependencies (`iproute`, `nftables`):

```bash
cd /path/to/mortgage

podman build --platform linux/amd64 \
  -t small-business-loan-agent:latest \
  -f Containerfile .

REGISTRY=default-route-openshift-image-registry.apps.ocp.qn6c5.sandbox1388.opentlc.com
podman tag small-business-loan-agent:latest $REGISTRY/loan-agent/small-business-loan-agent:latest
podman push $REGISTRY/loan-agent/small-business-loan-agent:latest
```

**Source**: [`Containerfile`](../Containerfile) — UBI9 + Python 3.12, installs `iproute nftables` for OpenShell supervisor, copies agent code + skills + corpus + server.

## Step 2: Deploy as AgentSandbox

The agent is deployed as an `agents.x-k8s.io/v1beta1 Sandbox` resource. The ArgoCD-managed manifests live in the `rrbanda/ai-platforms` repo.

**Key environment variables (from ConfigMap + SealedSecret):**

```yaml
# Model backend (MaaS)
- name: MAAS_BASE_URL
  value: "https://maas.apps.ocp.qn6c5.sandbox1388.opentlc.com"
- name: MAAS_API_KEY
  valueFrom:
    secretKeyRef:
      name: loan-agent-auth
      key: llm-api-key
- name: MAAS_SSL_VERIFY
  value: "false"
- name: MAAS_URL_PATH
  value: "/gemini-external/{model}/v1"

# Model
- name: MODEL_NAME
  value: "gemini-2.5-flash"

# AutoRAG
- name: AUTORAG_BASE_URL
  value: "http://autorag-ogx-service.autorag.svc.cluster.local:8321"
- name: AUTORAG_VECTOR_STORE_ID
  value: "vs_23c69157-2907-4576-8fe0-dc491de89d14"
- name: AUTORAG_SSL_VERIFY
  value: "false"

# State persistence
- name: STATE_DB_PATH
  value: "/app/data/state.db"

# Branding
- name: BANK_NAME
  value: "Cymbal Bank"
- name: AGENT_NAME
  value: "loan-agent"
- name: AGENT_HOST
  value: "loan-agent-loan-agent.apps.ocp.qn6c5.sandbox1388.opentlc.com"
```

### Rate Tier Configuration

Interest rates are configurable per deployment without code changes:

```yaml
- name: RATE_TIER_1
  value: "6.50"    # Low Risk
- name: RATE_TIER_2
  value: "7.75"    # Moderate Risk
- name: RATE_TIER_3
  value: "9.25"    # Elevated Risk
- name: RATE_TIER_4
  value: "11.00"   # High Risk
- name: DEFAULT_LOAN_TERM_MONTHS
  value: "60"
- name: INSURANCE_VERIFICATION_DAYS
  value: "30"
```

## Step 3: Apply Egress Policy

Create a policy file that restricts outbound traffic to only the required endpoints:

```yaml
# policy.yaml — L7 egress rules for the loan agent
sandbox:
  network:
    egress:
      # MaaS Gateway (LLM endpoint)
      - host: "maas.apps.ocp.qn6c5.sandbox1388.opentlc.com"
        port: 443
        methods: ["POST"]
        paths:
          - "/gemini-external/*/v1/chat/completions"
          - "/gemini-external/*/v1/completions"

      # AutoRAG / OGX (regulatory knowledge retrieval)
      - host: "autorag-ogx-service.autorag.svc.cluster.local"
        port: 8321
        methods: ["POST"]
        paths:
          - "/v1/vector_stores/*/search"

      # No other egress allowed — SQLite is local file I/O
```

Apply the policy:

```bash
openshell policy set loan-agent --policy policy.yaml --wait
```

## Step 4: Verify

```bash
BASE=https://loan-agent-loan-agent.apps.ocp.qn6c5.sandbox1388.opentlc.com

# Health check
curl -s $BASE/health | python3 -m json.tool
# {"status": "healthy", "agent_initialized": true}

# A2A Agent Card (capability discovery)
curl -s $BASE/.well-known/agent-card.json | python3 -m json.tool | head -30

# Status check (lightweight — only calls check_process_status)
curl -s -X POST $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is the status of loan application SBL-2026-00201?"}], "model": "loan-agent"}'

# Full loan application (triggers all 4 sub-agents)
curl -s -X POST $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Process loan application SBL-2026-10001. Business: Sunrise Bakehouse LLC. Owner: Morgan Ellis, morgan@sunrisebakehouse.com, 555-0201. Retail bakery, 5 years, 14 employees. Annual revenue $980K, net profit $62K, no debt. Requesting $180K for 60 months for oven purchase. Collateral: baking equipment $140K."}],
    "model": "loan-agent"
  }'
```

## Step 5: AutoRAG Corpus Seeding

The PostSync hook Job (`seed-loan-knowledge-base`) re-seeds automatically on each ArgoCD sync. To manually re-seed after corpus updates:

```bash
# Run from the mortgage/ directory after updating tools/corpus/**/*.md
AUTORAG_BASE_URL=http://autorag-ogx-service.autorag.svc.cluster.local:8321 \
  python3 tools/seed_autorag.py

# Copy the printed vector_store_id into the sandbox.yaml configmap and commit
```

**Corpus layout** (`tools/corpus/`):

| Domain | Files | Content |
|--------|-------|---------|
| `eligibility/` | 3 | SBA general eligibility, collateral requirements, 13 CFR § 120.110 prohibited businesses |
| `regulatory/` | 1 | 12 CFR § 1002.9 ECOA adverse action notification |
| `industry/` | 2 | NAICS prohibited codes, industry risk assessment guide |
| `pricing/` | 1 | Risk tier and rate guide |
| `faq/` | 2 | Applicant FAQ, reapplication guidance |

## Cleanup

```bash
# Delete the running pod (imagePullPolicy: Always pulls new image on restart)
oc delete pod -l app=loan-agent -n loan-agent

# Or delete the entire sandbox
oc delete sandbox loan-agent -n loan-agent
```

## Comparison: Local vs AgentSandbox Deployment

| Aspect | Local (`uv run adk web`) | AgentSandbox (OpenShell) |
|--------|--------------------------|--------------------------|
| Base image | Python 3.11+ (local venv) | UBI9 Python 3.12 |
| Network isolation | None | OpenShell L7 policy engine |
| Credential storage | `.env` file | SealedSecrets (encrypted in git) |
| State persistence | Local SQLite file | SQLite on PVC (survives restarts) |
| LLM backend | Gemini API key (direct) | MaaS Gateway (OpenAI-compatible) |
| AutoRAG | Optional (static fallback) | OGX with Milvus vector store |
| Skills | `skills/` directory (local) | Baked into container image at `/app/skills/` |
| API endpoint | `http://localhost:8000` (ADK Web) | Route with TLS at `:443` |
| Process supervision | Python process | OpenShell supervisor |
| Egress logging | None | OpenShell audits all connections |
| A2A discovery | Available at `/` (ADK Web) | `/.well-known/agent-card.json` |

## Secrets Management

| Secret | Contents | Rotation |
|--------|----------|----------|
| `loan-agent-auth` | `llm-api-key` (MaaS API key) | Re-seal and commit to `ai-platforms` repo |
| `openshell-client-tls` | `ca.crt`, `tls.crt`, `tls.key` | Managed by OpenShell gateway |

All secrets are SealedSecrets — encrypted at rest in the git repo, decrypted only inside the cluster by the SealedSecrets controller.

## Notes

- The agent uses the OpenAI-compatible `/chat/completions` API (via `server.py` FastAPI), not the ADK `adk web` server. This is required because the sandbox runs `uvicorn server:app` as its CMD.
- `MAAS_BASE_URL` must be reachable from within the sandbox. Use the cluster-external Route URL (not `svc.cluster.local`) since OpenShell may enforce egress by FQDN.
- `AUTORAG_BASE_URL` should use the cluster-internal service URL (`svc.cluster.local`) for lower latency.
- Build with `--platform linux/amd64` when targeting x86_64 clusters from Apple Silicon.
- The `STATE_DB_PATH` must point to the PVC mount (`/app/data/state.db`) — otherwise state is lost on pod restart.
