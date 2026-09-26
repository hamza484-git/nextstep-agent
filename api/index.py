"""Vercel serverless entry point for the NextStep Agent.

Two-stage boot:
  1. Fix sys.path so `nextstep_agent` is importable.
  2. Import the FastAPI `app` — top-level so Vercel's static analyser sees it.

If the import fails, we log a full stack trace + directory listing to stderr
BEFORE re-raising, so `vercel logs` shows exactly what went wrong.
"""
import os
import sys
import traceback
from pathlib import Path

_here = Path(__file__).resolve().parent          # /var/task/api
_root = _here.parent                              # /var/task
for _cand in [str(_root), str(_here), "/var/task"]:
    if _cand not in sys.path:
        sys.path.insert(0, _cand)


def _dump_diagnostics(msg: str):
    """Emit a bundle of debug info to stderr — visible in `vercel logs`."""
    print(f"\n===== nextstep-agent boot failure =====", file=sys.stderr, flush=True)
    print(f"reason: {msg}", file=sys.stderr, flush=True)
    print(f"cwd:    {os.getcwd()}", file=sys.stderr, flush=True)
    print(f"__file__: {__file__}", file=sys.stderr, flush=True)
    print(f"sys.path[:5]: {sys.path[:5]}", file=sys.stderr, flush=True)
    for probe in ["/var/task", "/tmp", str(_root)]:
        try:
            print(f"listing {probe}: {sorted(os.listdir(probe))[:15]}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"listing {probe} failed: {e}", file=sys.stderr, flush=True)
    print("---- traceback ----", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    print(f"====================================\n", file=sys.stderr, flush=True)


# Declare `app` at top level so Vercel's static analyser recognises it
# even when the actual import is inside try/except for diagnostics.
app = None  # type: ignore  # will be replaced by the real FastAPI app below

try:
    from nextstep_agent.api import app  # noqa: E402,F401
except Exception as _e:
    _dump_diagnostics(f"{type(_e).__name__}: {_e}")
    raise
