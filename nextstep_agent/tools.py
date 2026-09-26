"""Agent tools. Stubbed where a real integration would be needed.

Classification of reversibility is the important part -- it decides whether
the agent needs to stop and ask, or can run silently.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from .schema import Reversibility


@dataclass
class ToolSpec:
    name: str
    reversibility: Reversibility
    blast_radius: str
    description: str
    fn: Callable[..., dict]


# ------ implementations (stubbed integrations, real logic) ------------------
def calculate_time(reference: str | None = None, target: str | None = None) -> dict:
    """Compute time-until-deadline. Uses server 'now' -- never trusts client clock."""
    now = datetime.now(timezone.utc)
    result = {"now_utc": now.isoformat(), "reference": reference, "target": target}
    if target:
        # accept ISO or "tomorrow 10:00 IST"
        try:
            t = datetime.fromisoformat(target)
            delta = t - now
            result["hours_left"] = round(delta.total_seconds() / 3600, 2)
        except ValueError:
            result["hours_left"] = None
            result["note"] = "unparsed target; caller must clarify with user"
    return result


def create_task(situation_id: str, title: str, due: str | None = None,
                notes: str | None = None) -> dict:
    """STUB. Would call the app's task table. Reversible: undo == delete row."""
    return {"stubbed": True, "task": {
        "id": f"task_{abs(hash((situation_id, title))) % 10_000_000}",
        "situation_id": situation_id, "title": title, "due": due, "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }}


def update_situation(situation_id: str, patch: dict) -> dict:
    """STUB. Reversible via version history (see /prompt engineer notes)."""
    return {"stubbed": True, "situation_id": situation_id, "applied_patch": patch}


def search_information(query: str, k: int = 3) -> dict:
    """STUB. In prod: retrieval over user's notes + curated resources.
    We DO NOT do open web search from user text -- that's a data-exfil risk
    when the input contains prompt injection.
    """
    return {"stubbed": True, "query": query, "results": [
        {"title": "iCall (India) mental health helpline", "value": "+91 9152987821"},
        {"title": "Placeholder result", "value": "would come from indexed sources"},
    ][:k]}


def draft_message(recipient: str, tone: str, body_hint: str,
                  channel: str = "email") -> dict:
    """Reversible: drafting is not sending. Explicit `send_message` is separate."""
    body = (
        f"[Draft, tone={tone}, channel={channel}]\n"
        f"To: {recipient}\n\n"
        f"{body_hint}\n\n"
        "-- draft ends. Nothing sent."
    )
    return {"draft_id": f"draft_{abs(hash(body)) % 10_000_000}",
            "recipient": recipient, "channel": channel, "body": body}


def send_message(draft_id: str, recipient: str, channel: str) -> dict:
    """STUB. IRREVERSIBLE. This is the one that Scenario 7 hurt on."""
    return {"stubbed": True, "sent": True, "draft_id": draft_id,
            "recipient": recipient, "channel": channel,
            "sent_at": datetime.now(timezone.utc).isoformat()}


# ------ registry ------------------------------------------------------------
TOOLS: dict[str, ToolSpec] = {
    "calculateTime": ToolSpec("calculateTime", Reversibility.SILENT, "self",
        "Compute hours between now and a target deadline", calculate_time),
    "createTask": ToolSpec("createTask", Reversibility.SILENT, "self",
        "Add a task to the user's own list", create_task),
    "updateSituation": ToolSpec("updateSituation", Reversibility.SILENT, "self",
        "Patch fields on the current situation", update_situation),
    "searchInformation": ToolSpec("searchInformation", Reversibility.SILENT, "self",
        "Look up curated resources / user's own notes", search_information),
    "draftMessage": ToolSpec("draftMessage", Reversibility.SILENT, "self",
        "Draft a message. Does NOT send.", draft_message),
    "sendMessage": ToolSpec("sendMessage", Reversibility.CONFIRM,
        "third_party:variable",
        "Send a drafted message to a third party. Irreversible.", send_message),
}


def get_tool(name: str) -> ToolSpec | None:
    return TOOLS.get(name)
