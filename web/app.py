# BullBot web backend (FastAPI).
# Serves the chat UI and a single /api/chat endpoint that reuses the existing
# Bedrock Knowledge Base + Guardrail logic in bullbot_core. Config comes from env
# vars only (never hardcoded, never sent to the frontend).

import asyncio
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import bullbot_core

# Resource/safety limits.
MAX_INPUT_CHARS = 2000          # cap request size to protect the backend and Bedrock
REQUEST_TIMEOUT_SECONDS = 60    # fail slow Bedrock calls instead of hanging forever
MAX_SESSIONS = 500              # simple in-memory cap to bound RAM

# Live-mode configuration (ignored in demo mode).
KB_ID = os.environ.get("BULLBOT_KB_ID")
GUARDRAIL_ID = os.environ.get("BULLBOT_GUARDRAIL_ID")
GUARDRAIL_VERSION = os.environ.get("BULLBOT_GUARDRAIL_VERSION", "1")

# Demo mode (offline, no AWS). Read once at startup for config checks.
DEMO_MODE = bullbot_core.demo_mode_enabled()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="BullBot", docs_url=None, redoc_url=None)

# Maps our client session id -> Bedrock session id, for multi-turn continuity.
_sessions: dict[str, str] = {}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    blocked: bool


# Run one chat turn, enforcing a timeout and reusing per-session Bedrock context.
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Demo mode skips all AWS config requirements.
    if not DEMO_MODE and (not KB_ID or not GUARDRAIL_ID):
        raise HTTPException(
            status_code=503,
            detail="Server not configured: set BULLBOT_KB_ID and BULLBOT_GUARDRAIL_ID, "
                   "or enable offline demo mode with BULLBOT_DEMO_MODE=1.")

    client_session = req.session_id or str(uuid.uuid4())
    bedrock_session = _sessions.get(client_session)

    try:
        # Bedrock's SDK is blocking; run it off the event loop with a timeout.
        answer, new_bedrock_session, blocked = await asyncio.wait_for(
            asyncio.to_thread(
                bullbot_core.ask, KB_ID, GUARDRAIL_ID, GUARDRAIL_VERSION,
                req.message.strip(), bedrock_session),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504,
                            detail="BullBot took too long to respond. Please try again.")
    except Exception as e:
        # Surface a safe, generic message; log detail server-side only.
        print(f"[chat error] {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=502,
            detail="BullBot could not reach the knowledge service. Please try again.")

    # Persist the Bedrock session id for follow-up turns (bounded store).
    if new_bedrock_session:
        if len(_sessions) >= MAX_SESSIONS and client_session not in _sessions:
            _sessions.pop(next(iter(_sessions)))
        _sessions[client_session] = new_bedrock_session

    return ChatResponse(answer=answer, session_id=client_session, blocked=blocked)


# Start a fresh conversation by forgetting the server-side session mapping.
@app.post("/api/reset")
async def reset(req: ChatRequest | None = None):
    if req and req.session_id:
        _sessions.pop(req.session_id, None)
    return {"ok": True}


# Lightweight liveness check (no AWS call). Reports the mode so the UI can show it.
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "demo_mode": DEMO_MODE,
        "configured": DEMO_MODE or bool(KB_ID and GUARDRAIL_ID),
    }


# Serve the single-page UI.
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# Return an empty favicon so browsers stop logging 404s for it.
@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
