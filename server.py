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

"""FastAPI server wrapping the Small Business Loan Agent.

Follows the agentic-starter-kits ADK template pattern and exposes an
OpenAI-compatible /chat/completions endpoint.

Multi-turn sessions (required for human-in-the-loop approval):
  - First call: omit session_id → server generates one and returns it
  - Subsequent calls: pass the same session_id to continue the conversation
  - To approve a pending step: send {"content": "APPROVE", "session_id": "<id>"}

Environment variables (all from ConfigMap / Secret in the cluster):
  MAAS_BASE_URL, MAAS_API_KEY, MODEL_NAME   — model backend
  AUTORAG_BASE_URL, AUTORAG_VECTOR_STORE_ID  — RAG retrieval (optional)
  STATE_DB_PATH                              — SQLite path (default /app/data/state.db)
"""

import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field

# Load .env when running locally (no-op in container where env vars come from K8s)
dotenv.load_dotenv()

from small_business_loan_agent.agent import root_agent  # noqa: E402 — dotenv must load first

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

APP_NAME = "small_business_loan_agent"
USER_ID = "api_user"

_runner: InMemoryRunner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _runner
    _runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    logger.info("Agent runner initialized")
    yield
    _runner = None


app = FastAPI(
    title="Small Business Loan Agent API",
    description="OpenAI-compatible API for the ADK-based small business loan processing agent.",
    lifespan=lifespan,
)

v1 = APIRouter(prefix="/v1")


# ── Request / response models ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False
    session_id: str | None = Field(
        None,
        description="Pass the session_id from a prior response to continue the conversation.",
    )


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int
    message: ChoiceMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    session_id: str = Field(description="Pass this back to continue the conversation.")
    context: list[dict] | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _last_user_content(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    raise HTTPException(status_code=400, detail="No user message found")


async def _resolve_session(request: ChatCompletionRequest) -> str:
    """Return a valid session_id, creating a new session if none was supplied."""
    if _runner is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    if request.session_id:
        session = await _runner.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=request.session_id
        )
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {request.session_id!r} not found")
        return request.session_id
    session = await _runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    return session.id


async def _stream_completion(
    request: ChatCompletionRequest, session_id: str
) -> AsyncIterator[str]:
    """Async generator that yields OpenAI-compatible SSE chunks."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    agent_name = os.getenv("AGENT_NAME", "loan-agent")

    def sse(delta: dict, finish_reason: str | None = None) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": agent_name,
            "session_id": session_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    yield sse({"role": "assistant", "content": ""})

    user_content = _last_user_content(request.messages)
    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=user_content)]
    )

    tool_calls_emitted = 0
    try:
        async for event in _runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=new_message,
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.function_call:
                    args = dict(part.function_call.args or {})
                    args_str = json.dumps(args) if args else ""
                    line = f"> ⚙️ **{part.function_call.name}**"
                    if args_str and args_str != "{}":
                        line += f" `{args_str}`"
                    yield sse({"content": line + "\n\n"})
                    tool_calls_emitted += 1
                elif part.text and (event.content.role or "") == "model":
                    if tool_calls_emitted:
                        yield sse({"content": "---\n\n"})
                        tool_calls_emitted = 0
                    yield sse({"content": part.text})
    except Exception:
        logger.exception("Error in streaming agent run")

    yield sse({}, finish_reason="stop")
    yield "data: [DONE]\n\n"


# ── Endpoints ────────────────────────────────────────────────────────────────

@v1.get("/models")
async def list_models() -> dict:
    agent_name = os.getenv("AGENT_NAME", "loan-agent")
    return {
        "object": "list",
        "data": [{"id": agent_name, "object": "model", "owned_by": agent_name}],
    }


@v1.post("/chat/completions")
async def v1_chat_completions(request: ChatCompletionRequest):
    session_id = await _resolve_session(request)
    if request.stream:
        return StreamingResponse(
            _stream_completion(request, session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _run_completion(request, session_id)


@app.get("/health")
async def health() -> dict:
    initialized = _runner is not None
    body = {"status": "healthy" if initialized else "not_ready", "agent_initialized": initialized}
    if not initialized:
        return JSONResponse(status_code=503, content=body)
    return body


async def _run_completion(request: ChatCompletionRequest, session_id: str) -> dict:
    model_id = request.model or os.getenv("MODEL_NAME", "gemini-2.5-flash")
    user_content = _last_user_content(request.messages)
    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=user_content)]
    )

    final_text = ""
    context_messages: list[dict] = []

    try:
        async for event in _runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=new_message,
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.function_call:
                    context_messages.append({
                        "role": "assistant",
                        "content": f"Calling tool: {part.function_call.name}",
                        "tool_calls": [{
                            "type": "function",
                            "function": {
                                "name": part.function_call.name,
                                "arguments": json.dumps(dict(part.function_call.args or {})),
                            },
                        }],
                    })
                elif part.function_response:
                    context_messages.append({
                        "role": "tool",
                        "name": part.function_response.name,
                        "content": json.dumps(dict(part.function_response.response or {})),
                    })
                elif part.text:
                    role = event.content.role or "model"
                    context_messages.append({
                        "role": "assistant" if role == "model" else role,
                        "content": part.text,
                    })
                    if role == "model":
                        final_text = part.text
    except Exception:
        logger.exception("Error running agent")
        raise HTTPException(status_code=500, detail="Internal server error")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": final_text}, "finish_reason": "stop"}],
        "session_id": session_id,
        "context": context_messages,
    }


@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    if _runner is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    session_id = await _resolve_session(request)
    if request.stream:
        return StreamingResponse(
            _stream_completion(request, session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _run_completion(request, session_id)


app.include_router(v1)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
