"""MLflow tracing setup for the Small Business Loan Agent.

Follows the agentic-starter-kits ADK template pattern:
https://github.com/red-hat-data-services/agentic-starter-kits/blob/main/agents/google/templates/adk/src/adk_agent/tracing.py

Enable by setting MLFLOW_TRACKING_URI in the environment.
If the env var is absent or the server is unreachable, the agent starts normally without tracing.
"""

import logging
import time
from os import getenv
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)

_TRACING_ENABLED: bool = False


def _safe_uri(uri: str) -> str:
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(uri)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _check_mlflow_health(tracking_uri: str, max_wait: int = 5, retry_interval: int = 1) -> None:
    import requests
    url = f"{tracking_uri.rstrip('/')}/health"
    safe = _safe_uri(url)
    insecure = getenv("MLFLOW_TRACKING_INSECURE_TLS", "").lower() in ("true", "1", "yes")
    deadline = time.time() + max_wait
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError(f"MLflow unreachable after {max_wait}s at {safe}")
        try:
            resp = requests.get(url, timeout=min(5, remaining), verify=not insecure)
            if resp.status_code == 200:
                logger.info("[Tracing] MLflow health OK at %s", safe)
                return
            logger.warning("[Tracing] MLflow health returned %d at %s", resp.status_code, safe)
        except requests.exceptions.RequestException as exc:
            logger.warning("[Tracing] MLflow connect failed at %s: %s", safe, exc)
        if time.time() + retry_interval > deadline:
            raise RuntimeError(f"MLflow unreachable after {max_wait}s at {safe}")
        time.sleep(retry_interval)


def wrap_func_with_mlflow_trace(
    func: Callable, span_type: Literal["tool", "agent"], name: Optional[str] = None
) -> Callable:
    """Wrap a function with an MLflow span. No-op if tracing is disabled."""
    if not _TRACING_ENABLED:
        return func
    import mlflow
    from mlflow.entities import SpanType
    st = SpanType.TOOL if span_type == "tool" else SpanType.AGENT
    return mlflow.trace(span_type=st, name=name)(func)


def enable_tracing() -> None:
    """Enable MLflow tracing if MLFLOW_TRACKING_URI is set and reachable.

    Behavior:
    - MLFLOW_TRACKING_URI absent → tracing skipped, agent starts normally.
    - URI set but server unreachable → warning logged, agent starts normally.
    - URI set and server healthy → mlflow.litellm.autolog() enabled, all LLM
      calls captured as CHAT_MODEL spans in MLflow.
    """
    global _TRACING_ENABLED
    tracking_uri: Optional[str] = getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        logger.info("[Tracing] MLFLOW_TRACKING_URI not set — tracing disabled")
        return

    try:
        import mlflow
        import mlflow.litellm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MLFLOW_TRACKING_URI is set but mlflow is not installed. "
            "Install with: uv sync --extra tracing"
        ) from exc

    try:
        timeout = int(getenv("MLFLOW_HEALTH_CHECK_TIMEOUT", "5"))
    except ValueError:
        timeout = 5

    try:
        _check_mlflow_health(tracking_uri, max_wait=timeout)
    except RuntimeError as exc:
        logger.warning("[Tracing] %s — continuing without tracing", exc)
        return

    try:
        mlflow.set_tracking_uri(tracking_uri)
        experiment_name = getenv("MLFLOW_EXPERIMENT_NAME", "small-business-loan-agent")
        mlflow.set_experiment(experiment_name)
        mlflow.config.enable_async_logging()
        mlflow.litellm.autolog()
        _TRACING_ENABLED = True
        logger.info(
            "[Tracing] Enabled → %s  experiment=%s",
            _safe_uri(tracking_uri),
            experiment_name,
        )
    except Exception as exc:
        logger.warning("[Tracing] Setup failed, continuing without tracing: %s", exc)
