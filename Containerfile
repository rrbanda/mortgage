# Small Business Loan Agent — OCI container image
#
# Follows the agentic-starter-kits ADK template pattern:
# https://github.com/red-hat-data-services/agentic-starter-kits/tree/main/agents/google/templates/adk
#
# Build:
#   podman build --platform linux/amd64 -t small-business-loan-agent:latest -f Containerfile .
#
# Run locally (requires env vars — see .env.example):
#   podman run --env-file .env -p 8080:8080 small-business-loan-agent:latest

FROM registry.access.redhat.com/ubi9/python-312

USER 0

# iproute: required by OpenShell supervisor for network namespace management
# nftables: enables bypass detection (log + reject for direct connections)
RUN dnf install -y --nodocs iproute nftables && dnf clean all && rm -rf /var/cache/dnf

COPY --from=ghcr.io/astral-sh/uv@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce /uv /usr/local/bin/uv

RUN install -d -o 1001 -g 0 -m 775 /app /app/data
WORKDIR /app

COPY --chown=1001:0 pyproject.toml uv.lock* README.md ./
COPY --chown=1001:0 small_business_loan_agent/ ./small_business_loan_agent/
COPY --chown=1001:0 server.py .
RUN uv pip install --python /opt/app-root/bin/python3 --no-cache ".[server]"

USER 1001

ENV PORT=8080 \
    PYTHONPATH=/app \
    PATH="/opt/app-root/bin:${PATH}" \
    STATE_DB_PATH=/app/data/state.db

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
