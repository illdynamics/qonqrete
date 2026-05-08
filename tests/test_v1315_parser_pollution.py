import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

try:
    from instruqtor import extract_required_files_from_task
    from inspeqtor import extract_briq_file_targets
    from construqtor import extract_briq_target_files
except ModuleNotFoundError:
    from worqer.instruqtor import extract_required_files_from_task
    from worqer.inspeqtor import extract_briq_file_targets
    from worqer.construqtor import extract_briq_target_files

def test_instruqtor_rejects_numeric_decimals():
    # It should extract valid files but ignore the numeric 0.00002
    task_content = "Please generate `src/app.py` and `config.json` with learning rate `0.00002`."
    targets = extract_required_files_from_task(task_content)
    assert "src/app.py" in targets
    assert "config.json" in targets
    assert "0.00002" not in targets

def test_inspeqtor_rejects_numeric_decimals():
    briq_content = "Files to create: `src/main.js`, `1.2345.0` (Wait no, `0.00002`), `Dockerfile`"
    targets = extract_briq_file_targets(briq_content)
    assert "src/main.js" in targets
    assert "Dockerfile" in targets
    assert "0.00002" not in targets

def test_construqtor_rejects_numeric_decimals():
    briq_content = "Files to create: `src/main.js`, `0.00002`, `Makefile`"
    targets = extract_briq_target_files(briq_content)
    assert "src/main.js" in targets
    assert "Makefile" in targets
    assert "0.00002" not in targets


def test_construqtor_does_not_treat_object_properties_as_files():
    briq_content = """
Required files:
- app.js

Implementation detail:
- set `state.plan[day] = recipeId`
- read `state.recipes.length` when updating stats
"""
    targets = extract_briq_target_files(briq_content)
    assert "app.js" in targets
    assert "state.plan" not in targets
    assert "state.recipes" not in targets
