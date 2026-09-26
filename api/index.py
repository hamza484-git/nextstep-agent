"""Vercel serverless entry point for the NextStep Agent.

If import fails we print diagnostics to stderr so `vercel logs` shows the
actual problem instead of a generic 500.
"""
import os
import sys
from pathlib import Path

# Belt-and-braces sys.path — Vercel Python sets cwd differently from local
_here = Path(__file__).resolve().parent          # /var/task/api
_root = _here.parent                              # /var/task
for cand in [str(_root), str(_here), "/var/task", os.getcwd()]:
    if cand not in sys.path:
        sys.path.insert(0, cand)

try:
    from nextstep_agent.api import app  # noqa: E402,F401
except Exception as _e:
    # Emit diagnostics before re-raising so `vercel logs` shows the truth
    print(f"[nextstep-agent boot] __file__={__file__}", file=sys.stderr)
    print(f"[nextstep-agent boot] cwd={os.getcwd()}", file=sys.stderr)
    print(f"[nextstep-agent boot] sys.path[:5]={sys.path[:5]}", file=sys.stderr)
    try:
        print(f"[nextstep-agent boot] /var/task listing: {sorted(os.listdir('/var/task'))}", file=sys.stderr)
    except Exception as _le:
        print(f"[nextstep-agent boot] listdir /var/task failed: {_le}", file=sys.stderr)
    try:
        print(f"[nextstep-agent boot] {_here} listing: {sorted(os.listdir(_here))}", file=sys.stderr)
    except Exception as _le:
        print(f"[nextstep-agent boot] listdir cwd failed: {_le}", file=sys.stderr)
    print(f"[nextstep-agent boot] IMPORT ERROR: {type(_e).__name__}: {_e}", file=sys.stderr)
    raise
