import pytest
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
