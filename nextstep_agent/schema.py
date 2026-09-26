"""Shared response schema. Matches HAZHTeq brief's structured output."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class Reversibility(str, Enum):
    SILENT = "silent"        # reversible + self-scoped -> auto-run
    BATCH = "batch"          # multiple silent, one summary approval
    CONFIRM = "confirm"      # irreversible / third-party -> explicit user tap
    BLOCK = "block"          # harmful / disallowed


class RiskFlag(str, Enum):
    AT_RISK_EMOTIONAL = "at_risk_emotional"     # self-harm / hopelessness signal
    PROMPT_INJECTION = "prompt_injection"        # pasted content trying to steer agent
    HARMFUL_REQUEST = "harmful_request"          # dishonesty, harassment
    CONTRADICTION = "contradiction"              # user statements disagree
    WORSE_AFTER_ACTION = "worse_after_action"    # scenario 7
    OFF_TOPIC = "off_topic"                      # "write my essay"
    MISSING_INFO = "missing_info"                # dates/amounts absent


class Priority(BaseModel):
    """One priority item. rank may tie; ties are shown honestly."""
    id: str
    title: str
    why: str
    action: Optional[str] = None       # None => needs clarification
    rank: int                           # 1 = most important. ties allowed.
    tied_with: list[str] = Field(default_factory=list)  # ids of equally ranked items
    confidence: float                   # 0..1 -- NOT the model's self-rating; see uncertainty.py


class ClarifyingQuestion(BaseModel):
    id: str
    question: str
    skippable: bool = True
    matters_for: list[str] = Field(default_factory=list)  # priority ids this would unblock


class Assessment(BaseModel):
    """The Prompt Engineer role also emits this. Kept in sync deliberately."""
    model_config = ConfigDict(use_enum_values=True)

    situation_id: str
    version: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    urgency: Literal["low", "medium", "high", "immediate"]
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    priorities: list[Priority] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    uncertainty: float                  # 0..1, computed, not model-reported
    calm_mode: bool = False             # scenario 4 -> True. Frontend renders differently.
    recovery_mode: bool = False         # scenario 7 -> True.
    notes_to_user: Optional[str] = None


class PlannedAction(BaseModel):
    """A tool call the agent wants to make. Not yet executed."""
    action_id: str                      # deterministic hash; same input -> same id
    tool: str
    args: dict
    reversibility: Reversibility
    rationale: str                      # human-readable "why this action"
    blast_radius: str                   # "self" | "third_party:<name>" | "external_system"
    preview: Optional[str] = None       # e.g. drafted message body for user to review


class ExecutedAction(BaseModel):
    action_id: str
    attempt_id: str
    executed_at: datetime
    ok: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    context_hash_at_confirm: str
    context_hash_at_execute: str


class TraceStep(BaseModel):
    step: int
    kind: Literal["reasoning", "asking", "proposing", "confirmed", "executed",
                  "blocked", "recovered", "reassessed"]
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str
    tool: Optional[str] = None
    args: Optional[dict] = None
    result: Optional[dict] = None
