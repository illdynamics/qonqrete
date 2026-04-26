import sys
import os
from pathlib import Path
import json
import pytest

# Add worqer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "worqer"))

from instruqtor import (
    select_six_shooter_docs,
    write_six_shooter_manifest,
    analyze_task_complexity,
    compute_auto_repair_budget
)

def test_select_six_shooter_docs():
    # Small tier
    assert select_six_shooter_docs(1) == ["01", "02", "05"]
    assert select_six_shooter_docs(3) == ["01", "02", "05"]
    
    # Medium tier
    assert select_six_shooter_docs(4) == ["01", "02", "04", "05"]
    assert select_six_shooter_docs(7) == ["01", "02", "04", "05"]
    
    # Big tier
    assert select_six_shooter_docs(8) == ["00", "01", "02", "03", "04", "05"]
    assert select_six_shooter_docs(10) == ["00", "01", "02", "03", "04", "05"]

def test_manifest_generation(tmp_path):
    qontract_dir = tmp_path / "qontract.d"
    qontract_dir.mkdir()
    
    selected = ["01-execution-plan.md", "05-target-state.md"]
    complexity = {"score": 42.5}
    budget = {"retry_recommendation": 3, "repair_recommendation": 2}
    
    manifest_rel_path = write_six_shooter_manifest(
        workspace_root=tmp_path,
        selected_docs=selected,
        sensitivity=5,
        complexity_result=complexity,
        auto_repair_budget=budget
    )
    
    assert manifest_rel_path == "qontract.d/six-shooter-manifest.v1.json"
    manifest_path = tmp_path / manifest_rel_path
    assert manifest_path.exists()
    
    with open(manifest_path, "r") as f:
        data = json.load(f)
        
    assert data["schema_version"] == "six-shooter-manifest.v1"
    assert data["sensitivity"] == 5
    assert data["selected_docs"] == selected
    assert data["auto_repair_budget"] == budget
    assert data["tier"] == "medium"

def test_complexity_analysis():
    task = """
    # Big Project
    - Must do X
    - Shall do Y
    - Never do Z
    We need to update api/v1/users.py and models/user.py.
    Also implement a websocket handler for real-time updates.
    """
    result = analyze_task_complexity(task, qodeyard_file_count=10)
    assert "score" in result
    assert result["score"] > 0
    assert "websocket" in result["matched_keywords"]

def test_auto_repair_budget():
    config = {
        "retry": {"hard_cap_max_attempts": 6},
        "repair": {"hard_cap_max_attempts": 3}
    }
    plan_payload = {
        "estimation_basis": {
            "complexity": "high",
            "target_briqs": 15
        }
    }
    budget = compute_auto_repair_budget(
        config=config,
        plan_payload=plan_payload,
        sensitivity=8,
        required_files=["app.py", "db.py"]
    )
    assert budget["tier"] == "high"
    assert budget["retry_max_attempts"] > 2
    assert budget["repair_max_attempts_per_build_pass"] >= 1
