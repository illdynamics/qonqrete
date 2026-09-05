"""Python harness — runs unittest/pytest checks."""
from __future__ import annotations

from typing import List

from .base import Harness, HarnessContext, HarnessResult
from .shell import ShellHarness


class PythonTestHarness(Harness):
    """Runs Python tests using unittest or pytest."""

    def __init__(self, runner: str = "unittest"):
        self._runner = runner  # "unittest" or "pytest"

    @property
    def name(self) -> str:
        return f"python-{self._runner}-harness"

    def run(self, ctx: HarnessContext) -> HarnessResult:
        if self._runner == "pytest":
            cmd = "python -m pytest -q 2>&1"
        else:
            cmd = "python -m unittest discover -s . -v 2>&1"
        return ShellHarness([cmd]).run(ctx)
