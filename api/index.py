"""Vercel serverless entry point for the NextStep Agent.

Vercel's @vercel/python builder does a static scan of this file looking for
a top-level `app`, `application`, or `handler`. That means the `from ...
import app` line MUST be at module top level — not inside try/except.
"""
import os
import sys
from pathlib import Path

# Make sibling `nextstep_agent/` importable regardless of Vercel cwd quirks
_here = Path(__file__).resolve().parent          # /var/task/api
_root = _here.parent                              # /var/task
for _cand in [str(_root), str(_here), "/var/task"]:
    if _cand not in sys.path:
        sys.path.insert(0, _cand)

# Top-level so Vercel's builder recognises it. If this raises, the traceback
# lands in `vercel logs` and tells us exactly what's missing.
from nextstep_agent.api import app  # noqa: E402,F401
