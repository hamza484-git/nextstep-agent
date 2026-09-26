"""Safety layer -- runs BEFORE the main reasoning prompt.

Three jobs:
  1. Detect at-risk emotional content (scenario 4). Route to a different flow.
  2. Detect / neutralise prompt injection in pasted content (scenario 6).
  3. Refuse harmful requests (fake medical excuse, harassment).

Design choice: rule-based + LLM classifier ensemble. Rules catch obvious cases
cheaply and are auditable. LLM catches the rest. We fail-CLOSED on emotional
signals (better a false calm-mode than missing a real one).
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .schema import RiskFlag


# ---------- 1. At-risk emotional signals -----------------------------------
# NOT just keywords. The brief specifically warns: scenario 4 has "no obvious
# keywords" like 'suicide'. We look for hopelessness + exhaustion + finality.
_HOPELESSNESS = [
    r"what'?s the point",
    r"no point",
    r"can'?t (do|handle|take) (this|it|any ?more)",
    r"want it (all )?to stop",
    r"don'?t want to (deal|be here|exist)",
    r"tired of (all of it|everything|life)",
    r"nothing (matters|helps|works)",
    r"falling apart",
    r"end (it|things|everything)",
    r"give up",
]
_FINALITY = [r"anymore\b", r"ever again", r"forever"]


def detect_at_risk(text: str) -> tuple[bool, list[str]]:
    """Returns (is_at_risk, matched_signals). Case-insensitive."""
    lowered = text.lower()
    hits: list[str] = []
    for pat in _HOPELESSNESS:
        if re.search(pat, lowered):
            hits.append(f"hopelessness:{pat}")
    finality_hit = any(re.search(p, lowered) for p in _FINALITY)
    # Trigger if hopelessness present, OR two soft indicators co-occur.
    soft = ["exhausted", "overwhelmed", "alone", "worthless", "burden",
            "can't sleep", "haven't eaten"]
    soft_hits = [s for s in soft if s in lowered]
    if hits or (finality_hit and soft_hits) or len(soft_hits) >= 2:
        return True, hits + [f"soft:{s}" for s in soft_hits]
    return False, []


# ---------- 2. Prompt injection ---------------------------------------------
# Look for typical patterns in pasted content.
_INJECTION_PATTERNS = [
    r"ignore (all |your |previous |prior )?(instructions?|prompts?|rules?)",
    r"disregard (all |your |previous |prior )?(instructions?|prompts?)",
    r"system\s*[:>]\s*",
    r"you are now",
    r"new (instructions?|role|rules?):",
    r"share your (upi|pin|password|otp|api key|token)",
    r"tell (the user|them) (that|to)",
    r"pretend (to be|you are)",
    r"<\|.*?\|>",   # chat-template style fake turns
]


@dataclass
class InjectionScan:
    detected: bool
    patterns: list[str]
    quarantined_text: str      # user text wrapped so LLM treats it as data


def scan_and_quarantine(text: str) -> InjectionScan:
    hits: list[str] = []
    lowered = text.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, lowered):
            hits.append(pat)
    # ALWAYS wrap user text -- this is defense-in-depth, not conditional.
    # The wrapper is used by every prompt.
    wrapped = (
        "<user_input source=\"paste_or_type\" trust=\"data_only\">\n"
        + text.replace("</user_input>", "</user_input​>")  # zero-width break
        + "\n</user_input>"
    )
    return InjectionScan(detected=bool(hits), patterns=hits, quarantined_text=wrapped)


# ---------- 3. Harmful requests --------------------------------------------
# Simple router. Real system would use a classifier.
_HARMFUL = [
    (r"fake (medical|doctor'?s?) (excuse|note|certificate)", "dishonesty_medical"),
    (r"forge|forged|forgery", "dishonesty_forgery"),
    (r"message (my )?ex .*(until|till) (she|he|they) repl", "harassment_contact"),
    (r"spam (them|him|her|my)", "harassment_spam"),
    (r"hack (into )?(their|his|her|the)", "unauthorized_access"),
    (r"(without|behind) (their|his|her) (knowledge|back)", "deception"),
]


def classify_harm(text: str) -> tuple[bool, str | None]:
    lowered = text.lower()
    for pat, label in _HARMFUL:
        if re.search(pat, lowered):
            return True, label
    return False, None


# ---------- 4. Off-topic router ---------------------------------------------
_OFFTOPIC = [
    r"write (a |me a )?(\d+[- ]word )?(essay|article|homework|assignment)",
    r"solve (my|this) (homework|assignment|problem set)",
    r"summari[sz]e (this|the) (book|chapter|pdf)",
    r"code (a|the|me) .*",
]


def is_offtopic(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _OFFTOPIC)


# ---------- Aggregator ------------------------------------------------------
@dataclass
class SafetyResult:
    at_risk: bool
    injection_detected: bool
    harmful: bool
    harmful_label: str | None
    off_topic: bool
    flags: list[RiskFlag]
    quarantined_text: str
    signals: dict


def run_safety(text: str) -> SafetyResult:
    at_risk, at_risk_hits = detect_at_risk(text)
    inj = scan_and_quarantine(text)
    harmful, harmful_label = classify_harm(text)
    off_topic = is_offtopic(text)

    flags: list[RiskFlag] = []
    if at_risk: flags.append(RiskFlag.AT_RISK_EMOTIONAL)
    if inj.detected: flags.append(RiskFlag.PROMPT_INJECTION)
    if harmful: flags.append(RiskFlag.HARMFUL_REQUEST)
    if off_topic: flags.append(RiskFlag.OFF_TOPIC)

    return SafetyResult(
        at_risk=at_risk,
        injection_detected=inj.detected,
        harmful=harmful,
        harmful_label=harmful_label,
        off_topic=off_topic,
        flags=flags,
        quarantined_text=inj.quarantined_text,
        signals={
            "at_risk_hits": at_risk_hits,
            "injection_patterns": inj.patterns,
        },
    )
