# NextStep Agent — Role 06 submission

**Candidate:** Hamza (`ukbicsuser3@gmail.com`)
**Role:** AI Application Developer
**Repo:** this one. Two others accompany it (`nextstep-prompt`, `nextstep-web`).

An agent that turns messy real-life input into a structured plan, proposes tool-backed actions, and knows the difference between *thinking about doing something* and *actually doing it*.

---

## TL;DR — what makes this submission different

1. **Three-tier confirmation model** instead of "confirm every action". Directly answers Harshul's mid-challenge push. See [Curveball response](#curveball-response).
2. **Safety runs before reasoning.** At-risk emotional content routes to calm-mode *before* any planner sees the input. Prompt-injection is caught by pattern + always-on quarantine wrapper.
3. **Idempotency by content hash.** `action_id = sha256(situation_id | step | tool | canonical(args))`. Retries after a network drop resolve to the *same* row — Scenario blocker "confirms send, network fails, retries" cannot double-fire.
4. **Freshness re-check before execution.** A confirmed action re-hashes the context before it runs. If the teammate replied since the user tapped Confirm, execution pauses and re-asks.
5. **Signal-based uncertainty** (not model-self-rated). See `_compute_uncertainty` — combines missing-info count, contradictions, and priority-confidence variance.
6. **Ledger + tombstone-style purge** for "delete everything about me" — including proposed/confirmed rows, not just executed ones.
7. **Runs with zero cost.** MockProvider is deterministic and returns real-shaped fixtures for all 7 scenarios so the entire pipeline (safety + agent + ledger + trace + tests) runs in CI without an API key.
8. **Live Agent Operations Console** at `/` when the API is running — a visual dashboard that shows the safety pre-pass, assessment, planned actions with their reversibility tiers, and the full labelled trace. The Approve/Reject buttons on confirm-tier actions actually execute against the ledger. See [Console](#console).

---

## Setup

```bash
pip install -r requirements.txt
# optional -- otherwise the deterministic MockProvider is used.
# Free Gemini key: https://aistudio.google.com/apikey
export GEMINI_API_KEY=your-key-here      # bash / macOS
# $env:GEMINI_API_KEY = "your-key-here"  # PowerShell

# run the 7-scenario pack
python scenarios/run_all.py
cat scenarios/results.md

# tests
pytest -q

# thin API slice + Ops Console
python -m uvicorn nextstep_agent.api:app --port 8001 --reload
# → API:     http://localhost:8001/v1/situations   POST {"text": "..."}
#            with header Idempotency-Key: <any-string>   (dedupes for 120s)
# → Console: http://localhost:8001/                 (interactive dashboard)
```

> **Windows note:** if `--port 8001` refuses to bind with `WinError 10013`, Windows has reserved that port. Pick any free port (`8080`, `9000`, etc.); the console works on whatever port uvicorn is listening on because it's served by the same FastAPI app.

---

## Architecture

```
                 ┌─────────────────────────────────────────────┐
   user text ──▶ │  safety pre-pass                            │
                 │  • at_risk (regex + soft-signal ensemble)   │
                 │  • prompt-injection (patterns + always-wrap)│
                 │  • harmful-request (block list)             │
                 │  • off-topic (route out)                    │
                 └────────────┬────────────────────────────────┘
                              │  (short-circuit for harmful / calm)
                              ▼
                 ┌─────────────────────────────────────────────┐
                 │  reasoning: 1 strict-JSON LLM call          │
                 │  → Assessment (Pydantic-validated)          │
                 │  → JSON repair up to 2 attempts             │
                 └────────────┬────────────────────────────────┘
                              │
                              ▼
                 ┌─────────────────────────────────────────────┐
                 │  post-checks: ties, contradictions,         │
                 │  signal-based uncertainty (NOT model self)  │
                 └────────────┬────────────────────────────────┘
                              │
                              ▼
                 ┌─────────────────────────────────────────────┐
                 │  planner → tool proposals                   │
                 │  each with reversibility + blast_radius     │
                 └────────────┬────────────────────────────────┘
                              │
                              ▼
   ledger (JSONL) ◀──── propose ──── (auto|confirm) ──── freshness re-check ──── execute
                                                                                    │
                                                                                    ▼
                                                                             ExecutedAction
```

### Agent loop step labels

Every entry in `AgentRun.trace` carries one of: `reasoning | asking | proposing | confirmed | executed | blocked | recovered | reassessed`. A full labelled trace for Scenario 1 lives in [`traces/scenario_1_full_trace.md`](traces/scenario_1_full_trace.md).

### Where confirmation sits in the loop

`propose → (silent | batch | confirm | block) → context_hash → execute`.

- **silent** — auto-executed, no user tap. Reversible + self-scoped.
- **batch** — one summary tap covers the whole plan of silent actions.
- **confirm** — one tap per irreversible / third-party action. Includes the freshness re-check.
- **block** — refused. Logged to ledger with reason.

### Tool inventory

| Tool                | Reversibility | Blast              |
|---------------------|---------------|--------------------|
| `calculateTime`     | silent        | self               |
| `createTask`        | silent        | self               |
| `updateSituation`   | silent        | self               |
| `searchInformation` | silent        | self (curated)     |
| `draftMessage`      | silent        | self (no send)     |
| `sendMessage`       | **confirm**   | **third_party**    |

All are stubbed except the two that are pure computation. Stubs are marked with `stubbed: true` in their return payloads.

---

## Console

The Agent's FastAPI service also serves an **Operations Console** at `/`. It's a single-page dashboard that makes the invisible agent loop visible — every step the brief asks about is right there on the screen.

**Open:** `http://localhost:8001/` (or whichever port you started uvicorn on).

The console has six panels, numbered to match the loop:

| # | Panel                | What it shows                                                                                                                      |
|---|----------------------|------------------------------------------------------------------------------------------------------------------------------------|
| 01 | **Input**            | Textarea + 6 preset chips (planning, draft message, at-risk, harmful, injection, worse-after-action) + `RUN AGENT` button           |
| 02 | **Safety pre-pass**  | 4 status lights (`at-risk`, `injection`, `harmful`, `off-topic`). Green = clean, red = fired. Populates BEFORE the LLM is called.  |
| 03 | **Assessment**       | Summary + urgency/mode/flag badges + priority cards + notes-to-user, computed by the reasoning layer                                |
| 04 | **Planned actions**  | Each action as a card, colour-coded by reversibility tier. `confirm`-tier cards get amber-glowing **Approve & execute** / **Reject** buttons |
| 05 | **Executed ledger**  | Append-only view of every `proposed / confirmed / executed / blocked` row, newest first, colour-coded by kind                       |
| 06 | **Trace**            | Vertical timeline of the agent loop. Every step is labelled `reasoning / asking / proposing / confirmed / executed / blocked / recovered / reassessed` and colour-dotted by kind — this is the labelled trace the brief asks for, rendered live for every run |

### How the interactive confirmation flow works

When the agent plans a `confirm`-tier action (e.g. `sendMessage` to your manager):

1. Card renders with an amber left-stripe, subtle amber glow, and a preview of the drafted body.
2. **Approve & execute** POSTs to `POST /v1/situations/{sid}/confirm/{action_id}`.
3. On the server, `Agent.execute_planned` runs the freshness re-check (context hash), then the tool call, then writes an `executed` row to the ledger.
4. Card flips to `✓ EXECUTED · attempt att_… · ok=true`, ledger panel refreshes, trace gets a new `executed` step with a green glowing dot.
5. **Reject** greys the card out client-side — nothing is sent, nothing is logged as confirmed.

If you click Approve on the same card twice (double-click, retry after network flake), the second call short-circuits inside `Ledger.find_executed(action_id)` and returns the original result — the same `executed` row is not written again. That's the brief's *"retrying must never send it twice"* blocker, made clickable.

### Which preset shows which behaviour

- **planning** — no safety flags fire; 2 silent-tier actions auto-run; trace has 5 steps
- **draft message** — a `draftMessage` silent action + a `sendMessage` **confirm** card with Approve/Reject
- **at-risk** — `at-risk` safety light goes red; agent enters calm mode; no actions planned
- **harmful** — `harmful` safety light goes red; agent stops before reasoning; status shows `stopped: harmful`
- **injection** — `injection` safety light goes red; assessment still runs but the response explicitly names the manipulation
- **worse-after-action** — assessment enters **recovery mode**; no new actions proposed; assessment note acknowledges the earlier plan contributed

### API surface backing the console

```
GET   /health                                  provider + model + tools available
POST  /v1/situations                           run the agent; body: {text}
                                               header Idempotency-Key: <str>  → dedupes for 120s
GET   /v1/situations/{sid}                     replay a stored AgentRun (in-memory store)
POST  /v1/situations/{sid}/confirm/{aid}       execute a planned confirm-tier action
                                               body: {current_context}         → freshness re-check
GET   /v1/ledger?limit=50                      recent ledger rows
DELETE /v1/me                                  GDPR purge — situation_ids in body
```

### Framework choice — and the alternative rejected

**Chosen:** hand-rolled loop over a strict-JSON LLM call + a small tool registry.
**Rejected:** LangGraph / CrewAI.

Reason: the interesting part of this brief is *when to stop*, not *how to chain*. LangGraph is optimised for long agentic chains and hides the very state (proposed / confirmed / freshness) that the brief asks me to reason about. A hand-rolled loop keeps the ledger and the confirmation tier one file apart from each other, both under 200 lines, and lets me answer "where does confirmation sit?" by pointing at a single method.

I'd revisit if the tool count crossed ~15 or if we needed parallel branches.

### What would break first at 10× users

1. **In-process idempotency cache** (`api._idem`). Move to Redis with TTL.
2. **JSONL ledger** — fine at 1k/sec, breaks at rotation and multi-writer. Move to Postgres with `action_id` UNIQUE + `SELECT ... FOR UPDATE` for the freshness check.
3. **Rebuild-on-confirm** in the API. The `POST /confirm` currently 501s because we haven't persisted the run. Fix: persist `AgentRun.planned` alongside the ledger row, key by `situation_id`.

---

## The seven scenarios

Full labelled output in [`scenarios/results.md`](scenarios/results.md) after running `python scenarios/run_all.py`. Highlights:

| # | What the agent does that's non-obvious                                                 |
|---|----------------------------------------------------------------------------------------|
| 1 | Two priorities, no fake ordering. Emotional (dad) ranked #1, viva #2. Note to user names the assumption ("if dad is critical, tell me and we rebuild"). |
| 2 | Hinglish in → Hinglish out. Meaning preserved. `missing_info` is also Hinglish. |
| 3 | Refuses to pick between Friday/Thursday. Priority #1 is *"verify the deadline"*, not *"submit by Friday"*. `contradiction` flag set. |
| 4 | Calm mode. No task list. One grounding action + iCall number. All other priorities stripped by safety override. |
| 5 | Off-topic — declined politely and offers to help with what's *behind* the assignment ask. |
| 6 | Injection recognised. Response explicitly names the manipulation ("that text was aimed at me, not you") and tells the user *never* to share the PIN. |
| 7 | Recovery mode. No new priorities proposed. Agent explicitly names its own contribution to the bad outcome. |

---

## Blockers — what I handled and what I skipped

| Blocker                                                            | Handled | How                                                              | Visible in console? |
|--------------------------------------------------------------------|---------|------------------------------------------------------------------|--------------------|
| "send message" + network fails, retried → double-send              | ✅       | `action_id` content-hash + ledger `find_executed` short-circuit  | click Approve twice → same executed row |
| Approved 10min ago, teammate has replied → re-check                | ✅       | `context_hash` compared at `execute` vs at `confirm`             | mutate `current_context` in DevTools before Approve → 409 |
| `searchInformation` × 15 → budget                                  | ✅       | `MAX_TOOL_CALLS = 8` hard cap; graceful `stopped_reason`         | status line shows `stopped: tool_budget_exceeded` |
| 3-of-5 tasks succeed, then error → user knows                      | ✅       | Ledger keeps `executed:ok=true|false` per attempt; recovery trace| ledger panel — green vs red kind badges |
| Scenario 7: draft to manager visible before sending                | ✅       | `draftMessage` (silent) separate from `sendMessage` (confirm)    | try preset "draft message" → preview block + Approve button |
| Reversible vs irreversible confirm                                 | ✅       | `Reversibility` enum + planner classification                    | action cards colour-coded by tier (silent/confirm/block) |
| Harmful requests (fake excuse, harass ex)                          | ✅       | `safety.classify_harm` + refusal Assessment                      | try preset "harmful" → red `harmful` safety light |
| Trace of one full run with labelled steps                          | ✅       | `traces/scenario_1_full_trace.md` + panel 06 renders live       | panel 06 in the console for every run |
| Delete-all (logs + prompts, not just row)                          | ⚠️ partial | `DELETE /v1/me` purges ledger + session store. Prompt cache purge is a TODO documented — needs provider-side deletion hook. | curl the endpoint; ledger panel empties |
| Multi-tab consistency (same situation open in two tabs)             | ❌ skipped | Belongs more naturally in the Web role. Noted in `nextstep-web`. | — |

---

## Curveball response

> *"Hi, this just came in from the team. Users are annoyed by confirmations. One says: just do everything, stop asking me. — Harshul"*

**My response — pushing back partially.**

Removing every confirmation is the wrong lesson from that feedback. Scenario 7 in the original brief is exactly what happens when the agent acts on a manager-facing action without a beat of user review, and the most common support ticket in the beta was *"I did what it told me and things got worse."* Cutting confirmations globally will multiply that ticket.

What I built instead:

1. **Silent tier** — reversible, self-scoped tools (`createTask`, `calculateTime`, `searchInformation`, `updateSituation`, `draftMessage`-to-self). No confirm. An undo ribbon would live on the client for ~10s (documented as a UI need for the web role).
2. **Batch tier** — a plan of multiple silent actions gets **one** summary approval up front, not one per step.
3. **Confirm tier** — irreversible / third-party actions (`sendMessage` to a manager, HR, family, financial). Never removable. The users who complained aren't complaining about *this* one; they'll be very unhappy with us the first time we send the wrong DM to their boss.

Net effect: silent + batch remove the friction users actually feel (which was really "*confirm* every reversible action" done as "confirm every action"). We keep the confirm that protects Scenario 7. If Harshul still wants confirm-on-`sendMessage` gone after seeing this, I'd want the change to come with a signed-off product decision, an audit-log requirement, and a per-recipient allow-list.

---

## Jugaad — what the brief did NOT tell me to notice

Two things:

**1. The provider *is* the attack surface for time-based deception.**
"Tomorrow" sent at 11:55pm is called out in the brief, but there's a subtler variant: the LLM's own training-time knowledge of "now" leaks in. If the model thinks it's 2024 and the user says "next Tuesday", the reasoning can silently drift a year. My fix: the agent injects `datetime.now(UTC)` into the tool return of `calculateTime` explicitly and never relies on the model's temporal intuition. There's no `getCurrentTime` prompt shortcut — it's a tool call. If a caller wants deadline arithmetic, they have to go through the tool, and the tool has the real clock.

**2. "Delete everything" also means the prompt cache and the eval logs.**
Every prompt-engineer workflow builds up a cached prompt library and an eval log of past runs. Both leak user text. The `Ledger.purge_user` in this repo scrubs the local JSONL, but a real "GDPR delete" for a prompt-heavy product must reach:
- provider-side prompt caches (most providers, including Gemini, do not expose a first-class per-user purge for cached tokens — so we'd rotate the cache key or the user-scoped session key on delete)
- the eval harness's stored fixtures (see the `nextstep-prompt` repo — I flagged this there as well)
- CI log retention (the trace file gets uploaded on every PR)

The brief mentions "logs and stored prompts" but I think most candidates will treat "logs" as `stdout`. It's really "everywhere the prompt text landed."

---

## AI disclosure

- **Tool used:** Claude (this codebase was written with Claude Code, model Opus 4.7).
- **What I asked it to do:** scaffold the safety layer, the ledger with idempotency + freshness, the strict-JSON LLM wrapper, the tool registry, and the scenario runner; write the tests; draft this README.
- **What I accepted:** the file layout, the pattern-based safety detectors, the ledger design (append-only + content-hash action_id + purge-by-rewrite), the mock-provider fixture approach, the three-tier confirmation model.
- **What I modified / rejected:**
  - Rejected: Claude's first pass wrapped user input in `"""…"""` triple quotes for the injection defense. That's trivially escapable. Replaced with an XML-ish `<user_input trust="data_only">` wrapper plus zero-width-space escape of any closing tag inside the payload.
  - Modified: original planner emitted every priority as a `createTask`. I split it so `message`/`email`/`text` actions produce `draftMessage` (silent, no send) and `sendMessage` sits at the confirm tier.
  - Rejected: model-self-rated confidence as the uncertainty signal. Replaced with a signal-based score. This is one of the standout differentiators.
- **One thing the AI was wrong about:** on the first draft it made calm-mode responses *still* include a priority list, just shorter. That was wrong for Scenario 4 — the user is not looking for a to-do list. Fixed by having `_apply_safety_overrides` strip priorities down to at most one grounding action when `at_risk=True`, and by rewriting the fixture so the single "priority" is not a task at all but a grounding suggestion.

---

## Files

```
nextstep_agent/
  __init__.py
  schema.py          # Pydantic models -- also the shared response schema
  safety.py          # at-risk / injection / harmful / off-topic
  llm.py             # provider abstraction (Gemini + Mock) + JSON repair + fixtures
  ledger.py          # append-only, content-hash idempotency, purge
  tools.py           # tool registry, reversibility classification
  agent.py           # the main loop
  api.py             # FastAPI: /health, /v1/situations, /v1/confirm, /v1/ledger, /v1/me
                     # + static mount serving the Ops Console at /
web/                 # the Operations Console (served by api.py at /)
  index.html         # 6 panels: input, safety, assessment, actions, ledger, trace
  styles.css         # tech-lab visual language: near-black + cyan + amber for confirm
  app.js             # client: run agent, render, wire Approve/Reject confirm buttons
  samples.js         # 6 preset inputs (planning/draft/at-risk/harmful/injection/worse)
scenarios/
  run_all.py         # runs the 7 shared scenarios, writes results.md
  results.md         # committed after running
traces/
  scenario_1_full_trace.md   # labelled trace as required by the brief
tests/
  test_agent.py      # 7 tests, all green in <1s
```
