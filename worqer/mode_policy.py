#!/usr/bin/env python3
"""Centralized mode semantics for QonQrete execution policy."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
from pathlib import Path

PROGRAM_MODE = "program"
INNOVATIVE_MODE = "innovative"
MANDATORY_SCOPE_CLASS = "MANDATORY"
OPTIONAL_SCOPE_CLASS = "OPTIONAL_ENHANCEMENT"
ENHANCEMENT_TITLE_MARKER = "[ENHANCEMENT]"


@dataclass(frozen=True)
class ModePolicy:
    requested_mode: str
    semantic_mode: str
    freeze_execution_scope: bool
    allow_optional_enhancements: bool
    optional_enhancements_block_completion: bool
    mandatory_scope_class: str = MANDATORY_SCOPE_CLASS
    optional_scope_class: str = OPTIONAL_SCOPE_CLASS

    @property
    def description(self) -> str:
        if self.semantic_mode == PROGRAM_MODE:
            return "Freeze execution scope to the canonical task plus requirement ledger."
        return "Complete the canonical task first, but keep enhancement ideas optional unless explicitly promoted."

    def as_dict(self) -> dict:
        data = asdict(self)
        data["description"] = self.description
        return data


def normalize_mode(mode: str | None) -> str:
    raw = (mode or PROGRAM_MODE).strip().lower()
    return INNOVATIVE_MODE if raw == INNOVATIVE_MODE else PROGRAM_MODE


def load_mode_policy(mode: str | None) -> ModePolicy:
    requested = (mode or PROGRAM_MODE).strip() or PROGRAM_MODE
    semantic_mode = normalize_mode(requested)
    return ModePolicy(
        requested_mode=requested,
        semantic_mode=semantic_mode,
        freeze_execution_scope=(semantic_mode == PROGRAM_MODE),
        allow_optional_enhancements=(semantic_mode == INNOVATIVE_MODE),
        optional_enhancements_block_completion=False,
    )


def load_mode_policy_from_env() -> ModePolicy:
    return load_mode_policy(os.environ.get("QONQ_MODE", PROGRAM_MODE))


_SCOPE_RE = re.compile(r'^Scope-Class:\s*(.+)$', re.IGNORECASE | re.MULTILINE)


def extract_scope_class(text: str, title: str = "") -> str:
    match = _SCOPE_RE.search(text or "")
    if match:
        raw = match.group(1).strip().upper()
        if raw in {OPTIONAL_SCOPE_CLASS, "OPTIONAL", "ENHANCEMENT", "OPTIONAL-ENHANCEMENT"}:
            return OPTIONAL_SCOPE_CLASS
        return MANDATORY_SCOPE_CLASS

    if ENHANCEMENT_TITLE_MARKER in (title or "").upper():
        return OPTIONAL_SCOPE_CLASS
    return MANDATORY_SCOPE_CLASS


def is_optional_scope(scope_class: str | None) -> bool:
    return (scope_class or "").strip().upper() == OPTIONAL_SCOPE_CLASS


def classify_planned_briq(mode_policy: ModePolicy, title: str, content: str) -> str:
    detected = extract_scope_class(content, title)
    if mode_policy.semantic_mode == PROGRAM_MODE and detected == OPTIONAL_SCOPE_CLASS:
        return OPTIONAL_SCOPE_CLASS
    if mode_policy.semantic_mode != INNOVATIVE_MODE:
        return MANDATORY_SCOPE_CLASS
    return detected


def ensure_scope_class_line(text: str, scope_class: str) -> str:
    if _SCOPE_RE.search(text or ""):
        return _SCOPE_RE.sub(f"Scope-Class: {scope_class}", text, count=1)
    cleaned = (text or "").lstrip("\n")
    return f"Scope-Class: {scope_class}\n{cleaned}" if cleaned else f"Scope-Class: {scope_class}"


def read_mode_policy_artifact(worqspace_root: Path) -> ModePolicy:
    path = worqspace_root / 'qrystal.d' / 'mode_policy.json'
    if not path.exists():
        return load_mode_policy_from_env()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return load_mode_policy(data.get('semantic_mode') or data.get('requested_mode'))
    except Exception:
        return load_mode_policy_from_env()


def render_qrystallizer_directives(mode_policy: ModePolicy) -> str:
    if mode_policy.semantic_mode == PROGRAM_MODE:
        return (
            "MODE POLICY: PROGRAM. Freeze scope to the original tasq and canonical requirement ledger. "
            "Do not turn improvement ideas into requirements. Return an empty enhancement_backlog unless the tasq explicitly asks for optional ideas."
        )
    return (
        "MODE POLICY: INNOVATIVE. Keep the requirements ledger limited to canonical must/should work. "
        "You may propose extra improvements, but they MUST go into enhancement_backlog only and remain optional unless explicitly promoted later."
    )


def render_instruqtor_directives(mode_policy: ModePolicy) -> str:
    if mode_policy.semantic_mode == PROGRAM_MODE:
        return """
⚠️ **MODE POLICY: PROGRAM** ⚠️
- Execution scope is FROZEN to the explicit tasq and canonical requirement ledger.
- Every execution briq MUST be `Scope-Class: MANDATORY`.
- Extra ideas are allowed only as brief notes under `## Suggestions`; they MUST NOT become execution briqs.
- Done means the defined task is complete, not that new ideas were explored.
"""
    return """
💡 **MODE POLICY: INNOVATIVE** 💡
- Complete mandatory requirement-ledger work first.
- You MAY propose optional enhancement briqs, but they MUST be clearly separated with `Scope-Class: OPTIONAL_ENHANCEMENT`.
- Optional enhancement briqs MUST use `Requirement-IDs: NONE` unless the user explicitly promoted them into the canonical ledger.
- Optional enhancements are suggestion backlog only; they do NOT extend the mandatory stop condition.
"""


def render_construqtor_directives(mode_policy: ModePolicy, scope_class: str) -> str:
    base = [
        f"MODE POLICY: {mode_policy.semantic_mode.upper()}",
        f"BRIQ SCOPE CLASS: {scope_class}",
        "Implement ONLY the work explicitly described in this briq.",
        "Do not create follow-on features, hidden TODO scopes, or extra backlog items.",
    ]
    if mode_policy.semantic_mode == PROGRAM_MODE:
        base.append("Treat any extra ideas as suggestions only. Do not implement beyond the canonical requirement ledger.")
    elif is_optional_scope(scope_class):
        base.append("This briq is an optional enhancement. Keep it isolated and do not let it redefine what counts as done.")
    else:
        base.append("This briq is mandatory scope. Finish it cleanly without silently pulling in optional enhancements.")
    return "\n".join(f"- {line}" for line in base)


def render_inspeqtor_directives(mode_policy: ModePolicy) -> str:
    if mode_policy.semantic_mode == PROGRAM_MODE:
        return (
            "Review against the explicit task plus canonical requirement ledger only. "
            "Improvement ideas belong in suggestions and must not become blockers unless they were explicitly required."
        )
    return (
        "Review mandatory requirement-ledger work separately from optional enhancements. "
        "Optional enhancement failures must be reported, but they do not block SUCCESS when mandatory scope and required gates pass."
    )
