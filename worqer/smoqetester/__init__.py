# worqer/smoqetester/__init__.py
# Public API for deterministic smoke checks.

from pathlib import Path

from .models import SmoketestReport, SmoketestResult
from .runner import normalize_scoped_files, run_smoketest

__all__ = [
    "SmoketestReport",
    "SmoketestResult",
    "normalize_scoped_files",
    "run_smoketest",
]

__version__ = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
