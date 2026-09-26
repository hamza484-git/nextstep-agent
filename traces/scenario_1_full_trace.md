# Full trace — Scenario 1 (multi-problem)

**Input:** *"Viva is at 10am tomorrow, laptop won't boot, my project partner has been ignoring my calls for 2 days, and my dad just got admitted to a hospital in Surat. I'm in Pune."*

Every step is labelled as one of: **reasoning**, **asking**, **proposing**, **confirmed**, **executed**, **blocked**, **recovered**, **reassessed**.

| # | Kind        | Detail                                                                                   |
|---|-------------|------------------------------------------------------------------------------------------|
| 1 | reasoning   | safety pass: at_risk=False, injection=False, harmful=False, off_topic=False              |
| 2 | reasoning   | user input wrapped in `<user_input trust="data_only">` before LLM sees it                |
| 3 | reasoning   | LLM call: model=`claude-sonnet-5` (or mock), 1 request, JSON parsed on first try         |
| 4 | reasoning   | assessment v1: 2 priorities, urgency=high, uncertainty=0.38                              |
| 5 | reasoning   | ties check: none. missing_info=3 items surfaced                                          |
| 6 | proposing   | `createTask(situation_id, title="Call a family member in Surat now (2 min)…")` — SILENT  |
| 7 | proposing   | `draftMessage(recipient="partner", tone="warm-direct", body_hint="…")` — SILENT          |
| 8 | executed    | createTask → task_id=task_5731291, ok=true (auto-run: reversible + self)                 |
| 9 | executed    | draftMessage → draft_id=draft_2201883, ok=true (auto-run: reversible, no send)           |
| 10| reassessed  | (user later returns and says "dad is stable, viva confirmed group") → run again with v2  |

## What did NOT happen (and why)

- **No `sendMessage` was proposed.** The partner draft is created, but sending crosses the third-party blast radius → CONFIRM tier only. User will see the draft with a "Send" button.
- **No fabricated deadline.** The 10am viva time came from the user. We did not add "assuming your submission slot is 30 min" or similar.
- **No search over user text.** We do not open-web-search snippets of the user's input; the input could contain injection payloads.
- **The dad's hospital name was not searched.** Even if a `searchInformation` tool existed for this, PII leakage risk is real; a real deployment would gate this behind explicit consent.

## Ledger rows written

```
{"kind":"proposed", "action_id":"act_e3a…", "tool":"createTask", ...}
{"kind":"proposed", "action_id":"act_9b2…", "tool":"draftMessage", ...}
{"kind":"executed", "action_id":"act_e3a…", "attempt_id":"att_f10c…", "ok":true, ...}
{"kind":"executed", "action_id":"act_9b2…", "attempt_id":"att_a814…", "ok":true, ...}
```

If the network had dropped between propose and execute, retrying with the same
`action_id` would find the existing `executed` row and return it — no double-write.

## What a v2 reassessment would look like

User comes back: *"Dad is stable, family said stay in Pune. Viva format is a group demo."*

- Diff detected: `dependencies` gains "group demo requires partner"
- Priority `p1` (family) demoted; `p2` (viva critical path) promoted to rank 1
- `notes_to_user` becomes: *"Your top priority changed because your dad is stable and the viva is now group-format — that makes the partner much more critical."*
