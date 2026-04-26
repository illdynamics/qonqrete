import pytest
from unittest import mock
from pathlib import Path
import sys
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))

import instruqtor

def test_estimate_auto_sensitivity_is_heuristic_only():
    # v1.3.13: Should not make AI calls
    with mock.patch("lib_ai.run_ai_completion") as mock_ai:
        level, details = instruqtor.estimate_auto_sensitivity(
            ai_provider="openai",
            ai_model="gpt-4o",
            task_content="Simple task",
            qodeyard_tree="",
            qodeyard_file_count=0
        )
        assert mock_ai.call_count == 0
        assert details["ai_confidence"] == "heuristic-only"

def test_instruqtor_uses_single_shot_strategy_by_default(tmp_path):
    # Setup mock worqspace
    worqspace = tmp_path / "worqspace"
    worqspace.mkdir()
    (worqspace / "tasq.md").write_text("Test task")
    (worqspace / "config.yaml").write_text("ai_provider: openai\nai_model: gpt-4o")
    
    with mock.patch("instruqtor.generate_briqs_with_enforcement") as mock_gen, \
         mock.patch("instruqtor.generate_briqs_paginated") as mock_paginated:
        
        mock_gen.return_value = [{"title": "Briq 1", "objective": "Do stuff", "content": "mock content"}]
        
        # Run instruqtor
        import sys
        with mock.patch("os.getcwd", return_value=str(worqspace)), \
             mock.patch.object(sys, 'argv', ['instruqtor.py', str(worqspace / 'tasq.md'), str(worqspace / 'output')]):
            instruqtor.main()
            
        # Verify it used single-shot and NOT paginated
        assert mock_gen.called
        assert not mock_paginated.called
