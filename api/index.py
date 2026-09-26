"""Vercel serverless entry point for the NextStep Agent.

Vercel Python auto-detects an ASGI app exported as `app`. We re-export the
existing FastAPI app so this deployment shim never diverges from the local
uvicorn behaviour.

Local run (uvicorn):  python -m uvicorn nextstep_agent.api:app --port 8001
Vercel run:           this file is invoked per-request via @vercel/python
"""
import sys
from pathlib import Path

# The Vercel bundler places this file inside /var/task/api/. The rest of the
# repo (including nextstep_agent/) is at /var/task/. Add the parent so imports
# resolve the same way as `python -m uvicorn nextstep_agent.api:app`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nextstep_agent.api import app  # noqa: E402,F401  (re-exported for Vercel)
