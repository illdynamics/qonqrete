"""
Core data model for the Qq kernel.

These are intentionally boring and typed, per the "decision sediment" lesson
from QonQrete v1: every agent reads/writes these same shapes. No hidden
per-agent magic, no parallel ad-hoc dict schemas growing differently in
different files over a hundred patch commits.
"""
from __future__ import annotations
import dataclasses
import enum
import re
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional, Tuple
_SAFE_RE = re.compile('[^a-zA-Z0-9._-]')
_MAX_ID_LEN = 80

def slugify_id(raw: str, prefix: str='id') -> str:
    """Convert an arbitrary logical ID into a filesystem-safe physical ID.

    Rules:
    - Strip leading/trailing whitespace.
    - Replace runs of unsafe chars with a single hyphen.
    - Strip leading dots (prevents hidden-file / traversal confusion).
    - Collapse multiple hyphens.
    - Collapse repeated dots.
    - Remove .lock suffix (reserved git ref suffix).
    - Trim to max length.
    - Never empty.
    """
    raw = raw.strip()
    safe = _SAFE_RE.sub('-', raw)
    safe = re.sub('-{2,}', '-', safe)
    safe = re.sub('\\.{2,}', '.', safe)
    safe = safe.lstrip('.-')
    safe = safe.rstrip('.')
    if safe.endswith('.lock'):
        safe = safe[:-5]
    if len(safe) > _MAX_ID_LEN:
        safe = safe[:_MAX_ID_LEN].rstrip('-')
    safe = safe.rstrip('-')
    if not safe:
        safe = f'{prefix}-{uuid.uuid4().hex[:8]}'
    return safe

def _new_id(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:10]}'

def _now() -> float:
    return time.time()

class BriqStatus(str, enum.Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    AWAITING_REVIEW = 'awaiting_review'
    DONE = 'done'
    NEEDS_REPAIR = 'needs_repair'
    FAILED = 'failed'

class RunStatus(str, enum.Enum):
    CLARIFYING = 'clarifying'
    PLANNING = 'planning'
    BUILDING = 'building'
    HARNESSING = 'harnessing'
    REVIEWING = 'reviewing'
    REPAIRING = 'repairing'
    DONE = 'done'
    ABORTED = 'aborted'

@dataclasses.dataclass
class Task:
    id: str = dataclasses.field(default_factory=lambda: _new_id('task'))
    raw_text: str = ''
    created_at: float = dataclasses.field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

@dataclasses.dataclass
class ClarificationTurn:
    questions: List[str]
    answers: List[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class ClarifiedTask:
    id: str = dataclasses.field(default_factory=lambda: _new_id('ctask'))
    source_task_id: str = ''
    clarified_text: str = ''
    notes_for_instruqtor: str = ''
    transcript: List[ClarificationTurn] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_agent_json(cls, source_task_id: str, data: Dict[str, Any], transcript: List[ClarificationTurn]) -> 'ClarifiedTask':
        return cls(source_task_id=source_task_id, clarified_text=(data.get('clarified_task') or '').strip(), notes_for_instruqtor=(data.get('notes_for_instructor') or data.get('notes_for_instruqtor') or '').strip(), transcript=transcript)

@dataclasses.dataclass
class BriQ:
    id: str = dataclasses.field(default_factory=lambda: _new_id('briq'))
    safe_id: str = ''
    title: str = ''
    description: str = ''
    sensitivity: int = 5
    build_group_id: str = ''
    depends_on: List[str] = dataclasses.field(default_factory=list)
    expected_files: List[str] = dataclasses.field(default_factory=list)
    status: BriqStatus = BriqStatus.PENDING
    repair_notes: List[str] = dataclasses.field(default_factory=list)
    attempts: int = 0

    def __post_init__(self):
        if not self.safe_id:
            self.safe_id = slugify_id(self.id, 'briq')

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d['status'] = self.status.value
        return d

@dataclasses.dataclass
class BuildGroup:
    id: str = dataclasses.field(default_factory=lambda: _new_id('bg'))
    safe_id: str = ''
    name: str = ''
    description: str = ''
    briq_ids: List[str] = dataclasses.field(default_factory=list)
    parallel_safe: bool = False
    fully_accepted: bool = False

    def __post_init__(self):
        if not self.safe_id:
            self.safe_id = slugify_id(self.id, 'bg')

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d['safe_id'] = self.safe_id
        return d

@dataclasses.dataclass
class Plan:
    id: str = dataclasses.field(default_factory=lambda: _new_id('plan'))
    clarified_task_id: str = ''
    summary: str = ''
    briqs: Dict[str, BriQ] = dataclasses.field(default_factory=dict)
    build_groups: Dict[str, BuildGroup] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {'id': self.id, 'clarified_task_id': self.clarified_task_id, 'summary': self.summary, 'briqs': {k: v.to_dict() for k, v in self.briqs.items()}, 'build_groups': {k: v.to_dict() for k, v in self.build_groups.items()}}

    @classmethod
    def from_agent_json(cls, clarified_task_id: str, data: Dict[str, Any]) -> 'Plan':
        plan = cls(clarified_task_id=clarified_task_id, summary=data.get('summary', ''))
        seen_briq_ids: Dict[str, int] = {}
        seen_bg_ids: Dict[str, int] = {}
        for g in data.get('build_groups', []):
            raw_bg_id = g.get('build_group_id') or _new_id('bg')
            bg_id = _dedup_id(raw_bg_id, seen_bg_ids, 'bg')
            bg = BuildGroup(id=bg_id, name=g.get('name') or g.get('build_group_id', 'group'), description=g.get('description', ''), parallel_safe=bool(g.get('parallel_safe', False)))
            plan.build_groups[bg.id] = bg
            for b in g.get('briqs', []):
                raw_briq_id = b.get('briq_id') or _new_id('briq')
                briq_id = _dedup_id(raw_briq_id, seen_briq_ids, 'briq')
                sensitivity = b.get('sensitivity', 5)
                if not 0 <= sensitivity <= 16:
                    sensitivity = max(0, min(16, sensitivity))
                briq = BriQ(id=briq_id, title=b.get('title', ''), description=b.get('description', ''), sensitivity=sensitivity, build_group_id=bg.id, depends_on=b.get('depends_on', []) or [], expected_files=b.get('expected_files', []) or [])
                plan.briqs[briq.id] = briq
                bg.briq_ids.append(briq.id)
        all_ids = set(plan.briqs.keys())
        for briq in plan.briqs.values():
            briq.depends_on = [d for d in briq.depends_on if d in all_ids]
        return plan

    def validate(self) -> List[str]:
        issues: List[str] = []
        briq_to_groups: Dict[str, List[str]] = {}
        for bg in self.build_groups.values():
            for bid in bg.briq_ids:
                briq_to_groups.setdefault(bid, []).append(bg.id)
        for bid, gids in briq_to_groups.items():
            if len(gids) > 1:
                issues.append(f"briQ '{bid}' belongs to multiple groups: {gids}")
            elif len(gids) == 0:
                issues.append(f"briQ '{bid}' belongs to no build group")
        for bg in self.build_groups.values():
            for bid in bg.briq_ids:
                if bid not in self.briqs:
                    issues.append(f"build group '{bg.id}' references unknown briQ '{bid}'")
        return issues

def _dedup_id(raw: str, counter: Dict[str, int], prefix: str) -> str:
    n = counter.get(raw, 0) + 1
    counter[raw] = n
    if n == 1:
        return raw
    return f'{raw}-{n}'

@dataclasses.dataclass
class ReviewIssue:
    build_group_id: str
    briq_id: Optional[str]
    severity: str
    what_is_wrong: str
    what_to_fix: str
    files: List[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class ReviewVerdict:
    id: str = dataclasses.field(default_factory=lambda: _new_id('review'))
    cycle: int = 0
    status: str = 'NOT_DONE'
    summary: str = ''
    score: int = 0
    issues: List[ReviewIssue] = dataclasses.field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status.strip().upper() == 'FULLY_DONE'

    def to_dict(self) -> Dict[str, Any]:
        return {'id': self.id, 'cycle': self.cycle, 'status': self.status, 'score': self.score, 'summary': self.summary, 'issues': [dataclasses.asdict(i) for i in self.issues]}

    @classmethod
    def from_agent_json(cls, cycle: int, data: Dict[str, Any]) -> 'ReviewVerdict':
        raw_issues = data.get('issues', [])
        issues = [ReviewIssue(build_group_id=i.get('build_group_id', ''), briq_id=i.get('briq_id'), severity=i.get('severity', 'blocking'), what_is_wrong=i.get('what_is_wrong', ''), what_to_fix=i.get('what_to_fix', ''), files=i.get('files', []) or []) for i in raw_issues]
        status = data.get('status', 'NOT_DONE')
        summary = data.get('summary', '')
        score = data.get('score', 0)
        if not isinstance(score, int) or score < 0 or score > 100:
            score = 0
        verdict = cls(cycle=cycle, status=status, summary=summary, score=score, issues=issues)
        if verdict.passed and 'score' in data and (score < 95):
            verdict.status = 'NOT_DONE'
            verdict.issues = [ReviewIssue(build_group_id='', briq_id=None, severity='blocking', what_is_wrong=f'FULLY_DONE with score={score} (< 95) is inconsistent', what_to_fix='Achieve score >= 95 before declaring done')]
        if 'score' in data and score == 100 and issues:
            verdict.score = 90
            verdict.issues.append(ReviewIssue(build_group_id='', briq_id=None, severity='blocking', what_is_wrong='score=100 with non-empty issues is inconsistent', what_to_fix='Remove all issues or lower score'))
        if not verdict.passed and (not verdict.issues):
            verdict.issues = [_synthesize_blocking_issue(verdict)]
        return verdict

def _synthesize_blocking_issue(verdict: ReviewVerdict) -> ReviewIssue:
    content = verdict.summary.strip() or 'No specific issues provided by reviewer.'
    return ReviewIssue(build_group_id='', briq_id=None, severity='blocking', what_is_wrong=content, what_to_fix=f'Address reviewer concern: {content[:200]}')

@dataclasses.dataclass
class HarnessFailure:
    check_name: str
    exit_code: int
    stdout: str = ''
    stderr: str = ''
    duration_seconds: float = 0.0
    error_message: str = ''

@dataclasses.dataclass
class HarnessResult:
    passed: bool
    failures: List[HarnessFailure] = dataclasses.field(default_factory=list)
    total_checks: int = 0
    duration_seconds: float = 0.0

@dataclasses.dataclass
class RunState:
    run_id: str = dataclasses.field(default_factory=lambda: _new_id('run'))
    status: RunStatus = RunStatus.CLARIFYING
    cycle: int = 0
    max_cycles: int = 0
    max_time_seconds: int = 0
    workspace_root: str = ''
    task: Optional[Task] = None
    clarified_task: Optional[ClarifiedTask] = None
    plan: Optional[Plan] = None
    verdict_history: List[ReviewVerdict] = dataclasses.field(default_factory=list)
    harness_results: List[HarnessResult] = dataclasses.field(default_factory=list)
    build_results: Dict[str, Dict] = dataclasses.field(default_factory=dict)

    @property
    def last_verdict(self) -> Optional[ReviewVerdict]:
        return self.verdict_history[-1] if self.verdict_history else None