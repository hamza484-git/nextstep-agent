"""FastAPI slice for the NextStep Agent.

Endpoints:
  GET  /health                                        provider + model status
  POST /v1/situations                                 run the agent on new input
  GET  /v1/situations/{sid}                           replay a stored run
  POST /v1/situations/{sid}/confirm/{action_id}       execute a planned action
  GET  /v1/ledger?limit=50                            recent ledger rows
  DELETE /v1/me                                       purge everything about the user

Also mounts the Agent Operations Console static site at "/".
"""
from __future__ import annotations
import hashlib
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import Agent, AgentRun
from .ledger import Ledger, context_hash


app = FastAPI(title="NextStep Agent", version="0.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

_agent = Agent()

# Ledger path: on Vercel serverless the filesystem is read-only except /tmp,
# and /tmp doesn't persist across cold starts. Locally we use ./data/.
# For a production deployment we'd swap this for Redis or Postgres.
import os as _os
_IS_SERVERLESS = any(_os.getenv(k) for k in (
    "VERCEL", "VERCEL_URL", "VERCEL_ENV",
    "AWS_LAMBDA_FUNCTION_NAME", "LAMBDA_TASK_ROOT",
))
_LEDGER_PATH = _os.getenv("NEXTSTEP_LEDGER_PATH") or (
    "/tmp/nextstep_ledger.jsonl" if _IS_SERVERLESS else "./data/ledger.jsonl"
)
try:
    _ledger = Ledger(_LEDGER_PATH)
except (OSError, PermissionError):
    # Read-only filesystem, fall back to /tmp unconditionally
    _ledger = Ledger("/tmp/nextstep_ledger.jsonl")
_agent.ledger = _ledger      # keep the agent's ledger in sync with ours

# In-memory idempotency cache. Prod: Redis with TTL.
_idem: dict[str, tuple[float, dict]] = {}
_IDEM_TTL = 120

# In-memory session store, keyed by situation_id. Prod: Postgres row per run.
# We store the AgentRun object so /confirm can look up the planned actions.
_runs: dict[str, AgentRun] = {}


@app.get("/health")
def health():
    return {"ok": True, "provider": _agent.llm.name,
            "model": getattr(_agent.llm, "model", "?")}


class SituationIn(BaseModel):
    text: str
    situation_id: Optional[str] = None


def _serialize_run(sid: str, run: AgentRun) -> dict:
    return {
        "situation_id": sid,
        "assessment": run.assessment.model_dump(mode="json") if run.assessment else None,
        "planned": [p.model_dump(mode="json") for p in run.planned],
        "executed": [e.model_dump(mode="json") for e in run.executed],
        "trace": [t.model_dump(mode="json") for t in run.trace],
        "tool_calls_used": run.tool_calls_used,
        "stopped_reason": run.stopped_reason,
    }


@app.post("/v1/situations")
def submit(body: SituationIn, idempotency_key: str | None = Header(default=None)):
    key = idempotency_key or _hash(body.text)
    now = time.time()
    if key in _idem and now - _idem[key][0] < _IDEM_TTL:
        return _idem[key][1]
    sid = body.situation_id or "sit_" + hashlib.sha256(body.text.encode()).hexdigest()[:12]
    run = _agent.run(sid, body.text)
    _runs[sid] = run
    resp = _serialize_run(sid, run)
    resp["original_text"] = body.text     # useful for the console to render
    _idem[key] = (now, resp)
    return resp


@app.get("/v1/situations/{sid}")
def get_situation(sid: str):
    run = _runs.get(sid)
    if run is None:
        raise HTTPException(404, "situation not found in session store")
    return _serialize_run(sid, run)


class ConfirmIn(BaseModel):
    # A mutable context dict the caller believes is current. Passed through the
    # freshness check: if it hashes differently than what was stamped at confirm-
    # propose time, execution pauses.
    current_context: dict = {}


@app.post("/v1/situations/{sid}/confirm/{action_id}")
def confirm(sid: str, action_id: str, body: ConfirmIn):
    run = _runs.get(sid)
    if run is None:
        raise HTTPException(404, "situation not found in session store")
    ctx = body.current_context or {"situation_id": sid}
    try:
        executed = _agent.execute_planned(
            run, action_id=action_id, user_confirmed=True, current_context=ctx)
        return {"ok": True, "executed": executed.model_dump(mode="json"),
                "run": _serialize_run(sid, run)}
    except PermissionError as e:
        raise HTTPException(409, f"blocked: {e}")
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/v1/ledger")
def ledger(limit: int = 50):
    rows = _ledger.all()
    return {"count": len(rows), "rows": rows[-limit:]}


@app.delete("/v1/me")
def delete_me(situation_ids: list[str]):
    """GDPR-style purge. See README for the roadmap on prompt cache + logs."""
    n = _ledger.purge_user(situation_ids)
    for sid in situation_ids:
        _runs.pop(sid, None)
    return {"purged_rows": n}


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]


# --------- Static console at / ------------------------------------------------
# Serves ./web/ if it exists, otherwise ignored (allows the API to run headless).
_web_dir = Path(__file__).resolve().parents[1] / "web"
if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="console")
