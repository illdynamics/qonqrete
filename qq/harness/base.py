"""Harness base interface."""
from __future__ import annotations

import abc
import dataclasses
from typing import List


@dataclasses.dataclass
class HarnessFailure:
    check_name: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    error_message: str = ""


@dataclasses.dataclass
class HarnessResult:
    passed: bool
    failures: List[HarnessFailure] = dataclasses.field(default_factory=list)
    total_checks: int = 0
    duration_seconds: float = 0.0


@dataclasses.dataclass
class HarnessContext:
    """Context passed to harness checks."""
    run_id: str = ""
    cycle: int = 0
    repo_root: str = ""
    run_root: str = ""
    workspace_root: str = ""
    extra: dict = dataclasses.field(default_factory=dict)


class Harness(abc.ABC):
    """A deterministic check that validates the repo state.

    Harnesses run after ConstruQtor integration and before InspeQtor.
    If any harness fails, Qontroller creates structured repair issues
    and skips InspeQtor for that cycle (unless review_on_harness_failure
    is configured).
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @abc.abstractmethod
    def run(self, ctx: HarnessContext) -> HarnessResult:
        ...
