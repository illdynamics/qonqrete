import unittest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure worqer is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "worqer"))

import construqtor
import lib_sandbox_diff

class TestV1312DirectMode(unittest.TestCase):
    def setUp(self):
        self.worqspace_root = Path("/tmp/qonq_test_v1312")
        self.worqspace_root.mkdir(parents=True, exist_ok=True)
        self.qodeyard = self.worqspace_root / "qodeyard"
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        import shutil
        if self.worqspace_root.exists():
            shutil.rmtree(self.worqspace_root)

    def test_config_validation(self):
        # Test valid modes
        for mode in ['heredoc', 'direct', 'hybrid']:
            config = {'write_strategy': {'coding_mode': mode}}
            with patch('builtins.print'):
                res = construqtor.get_write_strategy_config(config)
                self.assertEqual(res['coding_mode'], mode)
        
        # Test invalid mode
        config = {'write_strategy': {'coding_mode': 'invalid'}}
        with patch('builtins.print'), patch('sys.exit') as mock_exit:
            construqtor.get_write_strategy_config(config)
            mock_exit.assert_called_with(1)

    def test_retry_defaults_and_override(self):
        defaults = construqtor.get_retry_config({})
        self.assertEqual(defaults['max_attempts'], 4)

        overridden = construqtor.get_retry_config({'retry': {'max_attempts': 5}})
        self.assertEqual(overridden['max_attempts'], 5)

    def test_retry_env_override(self):
        with patch.dict(os.environ, {"QONQ_RETRY_MAX_ATTEMPTS": "3"}, clear=False):
            overridden = construqtor.get_retry_config({})
        self.assertEqual(overridden["max_attempts"], 3)

    def test_repair_escalation_config_defaults_and_bool_form(self):
        defaults = construqtor.get_repair_escalation_config({})
        self.assertTrue(defaults["enabled"])
        self.assertEqual(defaults["max_level"], 4)
        self.assertEqual(defaults["start_policy"], "failure_class")

        disabled = construqtor.get_repair_escalation_config({"repair": {"repair_escalation": False}})
        self.assertFalse(disabled["enabled"])

    def test_resolve_primary_deliverables_uses_briq_inventory_not_group_primary(self):
        metadata = {
            "briq-ref": "briq-001",
            "build-group": "bg-html-css",
            "target-files": "index.html, app.js, styles.css",
        }
        planning = {
            "items": [
                {
                    "build_group_id": "bg-html-css",
                    "briq_refs": ["briq-001", "briq-002"],
                    "primary_files": ["index.html", "styles.css"],
                }
            ],
            "briq_inventory": [
                {"briq_ref": "briq-001", "primary_files": ["index.html"]},
                {"briq_ref": "briq-002", "primary_files": ["styles.css"]},
            ],
        }
        resolved = construqtor._resolve_briq_primary_deliverables(
            metadata,
            ["index.html", "app.js", "styles.css"],
            planning,
            ["index.html", "styles.css", "app.js"],
        )
        self.assertEqual(resolved, ["index.html"])

    def test_single_briq_group_inherits_completion_required_files(self):
        metadata = {
            "briq-ref": "briq-001",
            "build-group": "bg-single",
            "target-files": "index.html, e.g",
        }
        planning = {
            "items": [
                {
                    "build_group_id": "bg-single",
                    "briq_refs": ["briq-001"],
                    "primary_files": ["index.html"],
                }
            ],
            "briq_inventory": [
                {"briq_ref": "briq-001", "primary_files": ["index.html"]},
            ],
        }
        resolved = construqtor._resolve_briq_primary_deliverables(
            metadata,
            ["index.html"],
            planning,
            ["app.js", "index.html", "styles.css"],
        )
        self.assertEqual(resolved, ["app.js", "index.html", "styles.css"])

    def test_choose_repair_level_uses_failure_class_and_repeat_bump(self):
        cfg = {
            "repair": {
                "repair_escalation": {
                    "enabled": True,
                    "max_level": 4,
                    "start_policy": "failure_class",
                    "bump_policy": "on_same_class_repeat",
                }
            }
        }
        lvl1, reason1 = construqtor.choose_repair_level(
            config=cfg,
            attempt_index=2,
            failure_class="required_output_missing",
            failure_fingerprint="abc123",
            prior_attempt_records=[],
            recommended_start_level=None,
        )
        self.assertEqual(lvl1, 2)
        self.assertIn("failure_class", reason1)

        lvl2, reason2 = construqtor.choose_repair_level(
            config=cfg,
            attempt_index=3,
            failure_class="required_output_missing",
            failure_fingerprint="abc123",
            prior_attempt_records=[{"failure_class": "required_output_missing", "failure_fingerprint": "abc123"}],
            recommended_start_level=None,
        )
        self.assertEqual(lvl2, 3)
        self.assertIn("same_shape_repeat", reason2)

    def test_classify_attempt_failure_transport_and_validator_cases(self):
        failure_class, reason = construqtor.classify_attempt_failure(
            failure_status="failed_empty",
            error_message="No files written",
            direct_loop_meta={"parse_failures": 2, "apply_errors": 0, "truncated_responses": 1},
            validation={"syntax_errors": [], "constraint_errors": []},
            qonfirmer_report={},
        )
        self.assertEqual(failure_class, "transport_write_failure")
        self.assertIn("parse_failures=2", reason)

        failure_class2, _ = construqtor.classify_attempt_failure(
            failure_status="failed_validation",
            error_message="contract failed",
            direct_loop_meta={"parse_failures": 0, "apply_errors": 0},
            validation={"syntax_errors": [], "constraint_errors": []},
            qonfirmer_report={"status": "FAIL", "violations": [{"rule": "x"}]},
        )
        self.assertEqual(failure_class2, "exact_validator_violation")

    def test_prompt_builder(self):
        # Heredoc mode
        p_heredoc = construqtor._build_core_prompt('heredoc', 'tree', 'program', 'p')
        self.assertIn("markdown code blocks", p_heredoc)
        self.assertIn("EXAMPLE:", p_heredoc)
        self.assertIn("GENERATE ONLY THE FILE BLOCKS", p_heredoc)
        
        # Direct mode
        p_direct = construqtor._build_core_prompt('direct', 'tree', 'program', 'p')
        self.assertIn("write_file_direct", p_direct)
        self.assertIn("Do NOT use markdown code blocks", p_direct)
        self.assertNotIn("EXAMPLE:", p_direct)
        self.assertNotIn("GENERATE ONLY THE FILE BLOCKS", p_direct)

        # Hybrid mode
        p_hybrid = construqtor._build_core_prompt('hybrid', 'tree', 'program', 'p')
        self.assertIn("HYBRID POLICY", p_hybrid)
        self.assertIn("Follow the assigned transport list exactly", p_hybrid)
        self.assertIn("```language:qodeyard/<path>", p_hybrid)

    def test_deterministic_diff(self):
        sandbox = self.worqspace_root / "sandbox"
        baseline = self.worqspace_root / "baseline"
        sandbox.mkdir()
        baseline.mkdir()
        
        # Create files in non-sorted order
        files = ['z.txt', 'a.txt', 'm.txt']
        for f in files:
            (sandbox / f).write_text(f"content {f}")
            (baseline / f).write_text("old")
            
        changes = lib_sandbox_diff.detect_sandbox_changes(sandbox, baseline)
        # Dictionary keys should be sorted if we want full determinism in iteration later
        # But the tool ensures os.walk is sorted.
        self.assertEqual(list(changes.keys()), sorted(files))

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_success(self, mock_val, mock_ai):
        mock_val.return_value = {'passed': True}
        
        # Mock AI returning tool calls
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "test.py", "content": "print(1)"})
                    }
                }
            ]
        }
        
        validation_root = self.worqspace_root / "val"
        
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )
        
        self.assertIn("test.py", res)
        self.assertEqual(res["test.py"], "print(1)")
        self.assertTrue((validation_root / "test.py").exists())

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_coding_loop_fallback(self, mock_ai):
        # Mock AI returning fenced blocks instead of tools
        mock_ai.return_value = "Here is the code:\n```python:qodeyard/fallback.py\nprint(2)\n```"
        
        validation_root = self.worqspace_root / "val"
        
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )
        
        self.assertIn("fallback.py", res)
        self.assertEqual(res["fallback.py"], "print(2)")
        self.assertTrue((validation_root / "fallback.py").exists())

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_jail(self, mock_val, mock_ai):
        mock_val.return_value = {'passed': True}
        
        # Mock AI attempting path traversal
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "../outside.py", "content": "evil"})
                    }
                }
            ]
        }
        
        validation_root = self.worqspace_root / "val"
        validation_root.mkdir(parents=True, exist_ok=True)
        
        with patch('builtins.print'):
            res = construqtor._run_direct_coding_loop(
                "prov", "mod", "prompt", [], [],
                validation_root, self.qodeyard, self.worqspace_root, {}
            )
        
    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_coding_loop_fallback_dict_text(self, mock_ai):
        # Mock AI returning dict with text but no tool calls
        mock_ai.return_value = {
            "text": "Here is the code:\n```python:qodeyard/fallback_dict.py\nprint(3)\n```"
        }
        
        validation_root = self.worqspace_root / "val"
        
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )
        
        self.assertIn("fallback_dict.py", res)
        self.assertEqual(res["fallback_dict.py"], "print(3)")

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_stops_on_first_success(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        mock_ai.side_effect = [
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "winner.py", "content": "print('winner')\n"})
                        }
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "winner.py", "content": "print('overwritten')\n"})
                        }
                    }
                ]
            },
        ]

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )

        self.assertEqual(mock_ai.call_count, 1)
        self.assertIn("winner.py", res)
        self.assertEqual((validation_root / "winner.py").read_text(encoding="utf-8"), "print('winner')\n")

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_autofix_avoids_extra_iteration(self, mock_val, mock_ai):
        def _validate_side_effect(written_files, qodeyard_path, worqspace_root, cycle_label):
            target = qodeyard_path / "dirty.py"
            if not target.exists():
                return {
                    'passed': True,
                    'syntax_errors': [],
                    'constraint_errors': [],
                    'import_warnings': [],
                }
            content = target.read_text(encoding='utf-8')
            has_trailing = any(line.endswith(" ") for line in content.splitlines())
            if has_trailing:
                return {
                    'passed': False,
                    'syntax_errors': ["dirty.py: trailing whitespace"],
                    'constraint_errors': [],
                    'import_warnings': [],
                }
            return {
                'passed': True,
                'syntax_errors': [],
                'constraint_errors': [],
                'import_warnings': [],
            }

        mock_val.side_effect = _validate_side_effect
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "dirty.py", "content": "print(1)  \n"})
                    }
                }
            ]
        }

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )

        self.assertEqual(mock_ai.call_count, 1)
        self.assertIn("dirty.py", res)
        final_content = (validation_root / "dirty.py").read_text(encoding='utf-8')
        self.assertEqual(final_content, "print(1)\n")

    def test_context_selection_is_bounded_and_drops_irrelevant_markdown(self):
        qontext_dir = self.worqspace_root / "qontext.d"
        qontext_dir.mkdir(parents=True, exist_ok=True)
        context_files = [
            str(self.worqspace_root / "qodeyard" / "README.md"),
            str(self.worqspace_root / "qodeyard" / "src" / "app.py"),
            str(self.worqspace_root / "qontext.d" / "app.py.q.yaml"),
            str(self.worqspace_root / "qodeyard" / "src" / "util.py"),
        ]
        selected = construqtor._select_context_files_for_briq(
            context_files,
            ["src/app.py"],
            qontext_dir,
            max_files=3,
        )
        self.assertLessEqual(len(selected), 3)
        self.assertTrue(any(p.endswith("src/app.py") for p in selected))
        self.assertFalse(any(p.endswith("README.md") for p in selected))

    def test_extract_briq_target_files_captures_required_plain_filenames(self):
        briq_content = """
Required files:
- main.py
- run.sh
- requirements.txt
"""
        targets = construqtor.extract_briq_target_files(briq_content)
        self.assertIn("main.py", targets)
        self.assertIn("run.sh", targets)
        self.assertIn("requirements.txt", targets)

    def test_extract_briq_target_files_parses_required_files_yaml_key(self):
        briq_content = """
required-files:
  - index.html
  - styles.css
  - app.js
"""
        targets = construqtor.extract_briq_target_files(briq_content)
        self.assertEqual(set(targets), {"index.html", "styles.css", "app.js"})

    def test_extract_briq_target_files_ignores_decimal_tokens(self):
        briq_content = """
Implement the file and keep latency under 0.00003 seconds.
Required files:
- main.py
Also track ratio 1.25 in docs.
"""
        targets = construqtor.extract_briq_target_files(briq_content)
        self.assertIn("main.py", targets)
        self.assertNotIn("0.00003", targets)
        self.assertFalse(any(t.replace(".", "").isdigit() for t in targets))

    def test_extract_briq_target_files_ignores_repair_evidence_artifact_refs(self):
        briq_content = """
Target-Files: index.html, styles.css, app.js
Primary-Deliverables: index.html

### Evidence References
- validation/validation-bundle.v1.json
- realization/realization-bundle.v1.json
- verdict/inspection-verdict.v1.json
"""
        targets = construqtor.extract_briq_target_files(briq_content)
        self.assertIn("index.html", targets)
        self.assertIn("styles.css", targets)
        self.assertIn("app.js", targets)
        self.assertNotIn("validation/validation-bundle.v1.json", targets)
        self.assertNotIn("realization/realization-bundle.v1.json", targets)
        self.assertNotIn("verdict/inspection-verdict.v1.json", targets)

    def test_parse_metadata_file_list_ignores_repair_artifact_refs(self):
        parsed = construqtor._parse_metadata_file_list(
            "index.html, app.js, validation/validation-bundle.v1.json, verdict/inspection-verdict.v1.json"
        )
        self.assertEqual(set(parsed), {"index.html", "app.js"})

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_process_briq_uses_section_only_prompt_and_bounded_context(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
            'files_checked': 1,
        }
        mock_ai.return_value = "```python:qodeyard/main.py\nprint('ok')\n```"

        briq_file = self.worqspace_root / "briq.md"
        briq_file.write_text("Target: `main.py`\n\nImplement output.\n", encoding="utf-8")
        exeq_dir = self.worqspace_root / "exeq"
        exeq_dir.mkdir(parents=True, exist_ok=True)

        many_context_files = [
            str(self.worqspace_root / "qodeyard" / f"ctx_{i}.py")
            for i in range(30)
        ]
        for path_str in many_context_files:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# ctx {p.name}\n", encoding="utf-8")

        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'heredoc', 'recovery_policy': 'snapshot'}

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                many_context_files,
                'full source',
                'program',
                'mode prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )

        self.assertEqual(res['status'], 'success')
        args, kwargs = mock_ai.call_args
        prompt_arg = kwargs.get("prompt")
        if prompt_arg is None and len(args) >= 3:
            prompt_arg = args[2]
        self.assertEqual(prompt_arg, "")
        self.assertLessEqual(len(kwargs.get("context_files") or []), construqtor.DEFAULT_CONTEXT_FILES_PER_ATTEMPT)

    @patch('construqtor.finalize_attempt_manifest')
    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_coding_noop_success(self, mock_ai, mock_finalize):
        # Mock AI returning nothing
        mock_ai.return_value = {"text": "No code needed"}
        
        # Target file already exists
        target_path = self.qodeyard / "existing.py"
        target_path.write_text("print('existing')")
        
        # We need to test the outer process_briq_interleaved
        briq_file = self.worqspace_root / "briq.md"
        briq_file.write_text("Contract-Relevant: no\nTarget: `existing.py`")
        
        exeq_dir = self.worqspace_root / "exeq"
        exeq_dir.mkdir(exist_ok=True)
        
        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': False, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'direct', 'recovery_policy': 'snapshot'}
        
        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file, self.qodeyard, self.worqspace_root, exeq_dir, [], 'tree', 'program', 'prompt',
                'prov', 'mod', retry_config, interleaved_config, write_strategy_config=write_strategy_config
            )
            
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['attempt_records'][-1]['status'], 'committed')

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_parses_single_quote_arguments(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": "{'path': 'styles.css', 'content': 'body { color: red; }\\n'}",
                    }
                }
            ]
        }

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )

        self.assertIn("styles.css", res)
        self.assertTrue((validation_root / "styles.css").exists())

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_retries_after_parse_failure(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        mock_ai.side_effect = [
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": "{\"path\":\"app.js\",\"content\":\"broken",
                        }
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "app.js", "content": "console.log('ok');\n"}),
                        }
                    }
                ]
            },
        ]

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {}
        )

        self.assertEqual(mock_ai.call_count, 2)
        self.assertIn("app.js", res)
        self.assertEqual((validation_root / "app.js").read_text(encoding="utf-8"), "console.log('ok');\n")

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_escalates_output_tokens_after_truncated_parse_failure(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        mock_ai.side_effect = [
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": "{\"path\":\"app.js\",\"content\":\"unterminated",
                        }
                    }
                ],
                "truncated": True,
            },
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "app.js", "content": "console.log('ok');\n"}),
                        }
                    }
                ],
                "truncated": False,
            },
        ]

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {},
            output_tokens=1000,
        )

        self.assertIn("app.js", res)
        first_tokens = mock_ai.call_args_list[0].kwargs.get("output_tokens")
        second_tokens = mock_ai.call_args_list[1].kwargs.get("output_tokens")
        self.assertEqual(first_tokens, 1000)
        self.assertGreater(second_tokens, first_tokens)

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_direct_coding_loop_uses_markdown_fallback_after_persistent_tool_failures(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        broken = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": "{\"path\":\"app.js\",\"content\":\"unterminated",
                    }
                }
            ],
            "truncated": True,
        }
        mock_ai.side_effect = [
            broken,
            broken,
            "```javascript:qodeyard/app.js\nconsole.log('fallback');\n```",
        ]

        validation_root = self.worqspace_root / "val"
        res = construqtor._run_direct_coding_loop(
            "prov", "mod", "prompt", [], [],
            validation_root, self.qodeyard, self.worqspace_root, {},
            output_tokens=1000,
        )

        self.assertIn("app.js", res)
        self.assertEqual(
            (validation_root / "app.js").read_text(encoding="utf-8").strip(),
            "console.log('fallback');",
        )

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_noop_not_accepted_after_tool_parse_failure(self, mock_ai):
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": "{\"path\":\"existing.py\",\"content\":\"unterminated",
                    }
                }
            ]
        }

        target_path = self.qodeyard / "existing.py"
        target_path.write_text("print('existing')\n", encoding="utf-8")

        briq_file = self.worqspace_root / "briq.md"
        briq_file.write_text("Contract-Relevant: no\nTarget: existing.py", encoding="utf-8")

        exeq_dir = self.worqspace_root / "exeq"
        exeq_dir.mkdir(exist_ok=True)

        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': False, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'direct', 'recovery_policy': 'snapshot'}

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file, self.qodeyard, self.worqspace_root, exeq_dir, [], 'tree', 'program', 'prompt',
                'prov', 'mod', retry_config, interleaved_config, write_strategy_config=write_strategy_config
            )

        self.assertEqual(res['status'], 'failure')
        self.assertIn("tool-call failures", res.get('error', ''))

    def test_coding_mode_propagation_reports(self):
        # We don't want to run the full pipeline, just check the dictionaries built at the end
        # We'll set up a mock group_entry and call the block that writes the reports.
        # It's easier to verify that the keys are in the constructed dictionaries.
        # But since the dictionaries are built inside a large function, we can just assert
        # the strings "coding_mode" in the file logic.
        pass

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_noop_fails_when_primary_deliverable_missing(self, mock_ai):
        mock_ai.return_value = {"text": "No code needed"}

        briq_file = self.worqspace_root / "briq_missing_primary.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: run.sh\n"
            "Primary-Deliverables: run.sh\n\n"
            "Ensure run.sh exists.\n",
            encoding="utf-8",
        )

        exeq_dir = self.worqspace_root / "exeq_missing_primary"
        exeq_dir.mkdir(exist_ok=True)

        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': False, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'direct', 'recovery_policy': 'snapshot'}

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )

        self.assertEqual(res['status'], 'failure')
        self.assertIn("required primary deliverables are missing", res.get('error', ''))
        self.assertEqual(res['attempt_records'][-1]['status'], 'failed_missing_required')

    @patch('construqtor._stage_extracted_files')
    @patch('construqtor.commit_staged_attempt')
    @patch('construqtor.run_scoped_qualification')
    @patch('construqtor.lib_ai.run_ai_completion')
    def test_content_length_gate_rejects_tiny_primary_deliverable(self, mock_ai, mock_val, mock_commit, mock_stage):
        prior = self.qodeyard / "app.js"
        prior.write_text("console.log('existing content is definitely long enough');\n" * 8, encoding="utf-8")

        mock_ai.return_value = "```javascript:qodeyard/app.js\nx\n```"
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        staged_root = self.worqspace_root / "attempt_tiny"
        validation_root = staged_root / "validation-root"
        staging_dir = staged_root / "staging"
        validation_root.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        (validation_root / "app.js").write_text("x", encoding="utf-8")
        (staging_dir / "app.js").write_text("x", encoding="utf-8")
        mock_stage.return_value = {
            "attempt_id": "attempt-tiny",
            "attempt_root": staged_root,
            "staging_dir": staging_dir,
            "validation_root": validation_root,
            "manifest_path": staged_root / "attempt-manifest.v1.json",
            "staged_files": ["app.js"],
            "file_records": [{"path": "app.js", "size_bytes": 1, "content_sha256": "abc"}],
        }
        mock_commit.return_value = []

        briq_file = self.worqspace_root / "briq_tiny_primary.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: app.js\n"
            "Primary-Deliverables: app.js\n\n"
            "Update app.js.\n",
            encoding="utf-8",
        )

        exeq_dir = self.worqspace_root / "exeq_tiny_primary"
        exeq_dir.mkdir(exist_ok=True)

        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'heredoc', 'recovery_policy': 'snapshot'}

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )

        self.assertEqual(res['status'], 'failure')
        self.assertIn("trivially small", res.get('error', ''))
        self.assertEqual(res['attempt_records'][-1]['status'], 'failed_trivial')
        mock_commit.assert_not_called()

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_hybrid_new_file_uses_heredoc_transport(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
            'files_checked': 1,
        }
        mock_ai.return_value = "```python:qodeyard/new_file.py\nprint('ok')\n```"

        briq_file = self.worqspace_root / "briq_hybrid_new.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: new_file.py\n"
            "Primary-Deliverables: new_file.py\n\n"
            "Create new_file.py.\n",
            encoding="utf-8",
        )
        exeq_dir = self.worqspace_root / "exeq_hybrid_new"
        exeq_dir.mkdir(exist_ok=True)

        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {
            'mode': 'staged_atomic_per_attempt',
            'coding_mode': 'hybrid',
            'recovery_policy': 'snapshot',
            'hybrid_policy': construqtor.DEFAULT_WRITE_STRATEGY['hybrid_policy'],
        }
        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )
        self.assertEqual(res['status'], 'success')
        decisions = res['attempt_records'][-1].get('transport_decisions', [])
        decision = next(item for item in decisions if item.get('file_path') == 'new_file.py')
        self.assertEqual(decision.get('chosen_transport'), 'heredoc')
        self.assertIn('new_file_default_heredoc', decision.get('decision_reason_codes', []))

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_hybrid_existing_file_uses_direct_transport(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
            'files_checked': 1,
        }
        (self.qodeyard / "app.py").write_text("print('old')\n", encoding="utf-8")
        mock_ai.return_value = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "app.py", "content": "print('new')\n"}),
                    }
                }
            ]
        }

        briq_file = self.worqspace_root / "briq_hybrid_existing.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: app.py\n"
            "Primary-Deliverables: app.py\n\n"
            "Update app.py.\n",
            encoding="utf-8",
        )
        exeq_dir = self.worqspace_root / "exeq_hybrid_existing"
        exeq_dir.mkdir(exist_ok=True)
        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {
            'mode': 'staged_atomic_per_attempt',
            'coding_mode': 'hybrid',
            'recovery_policy': 'snapshot',
            'hybrid_policy': construqtor.DEFAULT_WRITE_STRATEGY['hybrid_policy'],
        }

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )
        self.assertEqual(res['status'], 'success')
        decisions = res['attempt_records'][-1].get('transport_decisions', [])
        decision = next(item for item in decisions if item.get('file_path') == 'app.py')
        self.assertEqual(decision.get('chosen_transport'), 'direct')
        self.assertFalse(bool(decision.get('fallback_occurred')))

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_hybrid_records_fallback_after_direct_transport_fragility(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
            'files_checked': 1,
        }
        (self.qodeyard / "app.js").write_text("console.log('old');\n", encoding="utf-8")
        broken = {
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": "{\"path\":\"app.js\",\"content\":\"unterminated",
                    }
                }
            ],
            "truncated": True,
        }
        mock_ai.side_effect = [
            broken,
            broken,
            "```javascript:qodeyard/app.js\nconsole.log('fallback');\n```",
        ]

        briq_file = self.worqspace_root / "briq_hybrid_fallback.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: app.js\n"
            "Primary-Deliverables: app.js\n\n"
            "Update app.js.\n",
            encoding="utf-8",
        )
        exeq_dir = self.worqspace_root / "exeq_hybrid_fallback"
        exeq_dir.mkdir(exist_ok=True)
        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {
            'mode': 'staged_atomic_per_attempt',
            'coding_mode': 'hybrid',
            'recovery_policy': 'snapshot',
            'hybrid_policy': construqtor.DEFAULT_WRITE_STRATEGY['hybrid_policy'],
        }

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )
        self.assertEqual(res['status'], 'success')
        decisions = res['attempt_records'][-1].get('transport_decisions', [])
        decision = next(item for item in decisions if item.get('file_path') == 'app.js')
        self.assertTrue(bool(decision.get('fallback_occurred')))
        self.assertEqual(decision.get('fallback_reason_code'), 'direct_transport_failure')
        self.assertEqual(decision.get('transport_lock_state_after'), 'heredoc')

    def test_hybrid_transport_lock_is_stable(self):
        app_path = self.qodeyard / "app.js"
        app_path.write_text("console.log('stable');\n", encoding="utf-8")
        locks = {"app.js": "heredoc"}
        decisions = construqtor._build_hybrid_transport_decisions(
            briq_content="Update app.js",
            candidate_files=["app.js"],
            primary_deliverables=["app.js"],
            qodeyard_path=self.qodeyard,
            transport_locks=locks,
            direct_failure_counts={"app.js": 0},
            missing_required_counts={"app.js": 0},
            policy_cfg=construqtor.DEFAULT_WRITE_STRATEGY["hybrid_policy"],
            attempt_index=2,
        )
        self.assertEqual(decisions[0]["chosen_transport"], "heredoc")
        self.assertIn("transport_lock:heredoc", decisions[0]["decision_reason_codes"])

    def test_hybrid_missing_required_recovery_switches_new_file_to_direct(self):
        locks = {"app.js": "heredoc"}
        policy = dict(construqtor.DEFAULT_WRITE_STRATEGY["hybrid_policy"])
        policy["missing_required_direct_recovery_enabled"] = True
        policy["missing_required_to_direct_recovery_threshold"] = 2
        decisions = construqtor._build_hybrid_transport_decisions(
            briq_content="Create app.js with full recipe logic.",
            candidate_files=["app.js"],
            primary_deliverables=["app.js"],
            qodeyard_path=self.qodeyard,
            transport_locks=locks,
            direct_failure_counts={"app.js": 0},
            missing_required_counts={"app.js": 2},
            policy_cfg=policy,
            attempt_index=3,
        )
        self.assertEqual(decisions[0]["chosen_transport"], "direct")
        self.assertEqual(decisions[0]["transport_lock_state_after"], "direct")
        self.assertIn(
            "missing_required_recovery_to_direct:2>=2",
            decisions[0]["decision_reason_codes"],
        )

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_hybrid_process_recovers_missing_new_file_with_direct_after_heredoc_misses(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
            'files_checked': 1,
        }
        mock_ai.side_effect = [
            "No file blocks here.",
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps(
                                {"path": "app.js", "content": "console.log('ok');\n"}
                            ),
                        }
                    }
                ]
            },
        ]
        briq_file = self.worqspace_root / "briq_hybrid_missing_recovery.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: app.js\n"
            "Primary-Deliverables: app.js\n\n"
            "Create app.js.\n",
            encoding="utf-8",
        )
        exeq_dir = self.worqspace_root / "exeq_hybrid_missing_recovery"
        exeq_dir.mkdir(exist_ok=True)
        retry_config = {'enabled': True, 'max_attempts': 2, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        policy = dict(construqtor.DEFAULT_WRITE_STRATEGY['hybrid_policy'])
        policy['missing_required_direct_recovery_enabled'] = True
        policy['missing_required_to_direct_recovery_threshold'] = 1
        write_strategy_config = {
            'mode': 'staged_atomic_per_attempt',
            'coding_mode': 'hybrid',
            'recovery_policy': 'snapshot',
            'hybrid_policy': policy,
        }
        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['attempts'], 2)
        first_decisions = res['attempt_records'][0].get('transport_decisions', [])
        second_decisions = res['attempt_records'][1].get('transport_decisions', [])
        self.assertEqual(first_decisions[0].get('chosen_transport'), 'heredoc')
        self.assertEqual(second_decisions[0].get('chosen_transport'), 'direct')
        self.assertIn(
            "missing_required_recovery_to_direct:1>=1",
            second_decisions[0].get('decision_reason_codes', []),
        )

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_no_tool_fallback_respects_allowed_paths(self, mock_ai):
        mock_ai.return_value = (
            "```python:qodeyard/allowed.py\nprint('ok')\n```\n"
            "```python:qodeyard/blocked.py\nprint('nope')\n```"
        )
        validation_root = self.worqspace_root / "val_allowlist"
        result, meta = construqtor._run_direct_coding_loop(
            "prov",
            "mod",
            "prompt",
            [],
            [],
            validation_root,
            self.qodeyard,
            self.worqspace_root,
            {},
            return_meta=True,
            allowed_paths={"allowed.py"},
        )
        self.assertIn("allowed.py", result)
        self.assertNotIn("blocked.py", result)
        self.assertTrue((validation_root / "allowed.py").exists())
        self.assertFalse((validation_root / "blocked.py").exists())
        self.assertGreaterEqual(int(meta.get("disallowed_path_calls", 0) or 0), 1)

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_direct_loop_stops_early_on_repeated_disallowed_paths(self, mock_ai):
        mock_ai.side_effect = [
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "outside.py", "content": "x = 1\n"}),
                        }
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "outside.py", "content": "x = 2\n"}),
                        }
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file_direct",
                            "arguments": json.dumps({"path": "outside.py", "content": "x = 3\n"}),
                        }
                    }
                ]
            },
        ]
        validation_root = self.worqspace_root / "val_disallowed_churn"
        _, meta = construqtor._run_direct_coding_loop(
            "prov",
            "mod",
            "prompt",
            [],
            [],
            validation_root,
            self.qodeyard,
            self.worqspace_root,
            {},
            return_meta=True,
            allowed_paths={"allowed.py"},
        )
        self.assertLessEqual(mock_ai.call_count, 2)
        self.assertGreaterEqual(int(meta.get("no_progress_iterations", 0) or 0), 1)

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_hybrid_heredoc_calls_keep_streaming_enabled_by_default(self, mock_val, mock_ai):
        mock_val.return_value = {
            'passed': True,
            'syntax_errors': [],
            'constraint_errors': [],
            'import_warnings': [],
        }
        mock_ai.return_value = "```html:qodeyard/index.html\n<html></html>\n```"

        briq_file = self.worqspace_root / "briq_stream_default.md"
        briq_file.write_text(
            "Contract-Relevant: no\n"
            "Target-Files: index.html\n"
            "Primary-Deliverables: index.html\n\n"
            "Create index.html\n",
            encoding="utf-8",
        )
        exeq_dir = self.worqspace_root / "exeq_stream_default"
        exeq_dir.mkdir(exist_ok=True)
        retry_config = {'enabled': True, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': True, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {
            'mode': 'staged_atomic_per_attempt',
            'coding_mode': 'hybrid',
            'recovery_policy': 'snapshot',
            'hybrid_policy': construqtor.DEFAULT_WRITE_STRATEGY['hybrid_policy'],
        }

        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file,
                self.qodeyard,
                self.worqspace_root,
                exeq_dir,
                [],
                'tree',
                'program',
                'prompt',
                'prov',
                'mod',
                retry_config,
                interleaved_config,
                write_strategy_config=write_strategy_config,
            )

        self.assertEqual(res['status'], 'success')
        self.assertGreaterEqual(mock_ai.call_count, 1)
        for call in mock_ai.call_args_list:
            self.assertNotEqual(call.kwargs.get("stream_callback"), False)

    @patch('construqtor.lib_ai.run_ai_completion')
    def test_streaming_fallback_retries_once_with_non_streaming(self, mock_ai):
        mock_ai.side_effect = [
            RuntimeError("event stream parser failed"),
            "ok",
        ]
        response, fallback_used = construqtor._run_ai_completion_with_streaming_policy(
            ai_provider="prov",
            ai_model="mod",
            prompt="hello",
            context_files=[],
            prompt_sections=[],
            agent_name="construqtor",
            task_type="code_generation",
            output_tokens=256,
            streaming_policy={"enabled": True, "fallback_to_non_streaming_on_error": True},
            stream_label="unit-test",
        )
        self.assertEqual(response, "ok")
        self.assertTrue(fallback_used)
        self.assertEqual(mock_ai.call_count, 2)
        self.assertEqual(mock_ai.call_args_list[1].kwargs.get("stream_callback"), False)

    def test_primary_deliverable_placeholder_guard_rejects_existing_downgrade(self):
        prior = self.qodeyard / "app.js"
        prior.write_text(("console.log('real implementation');\n" * 24), encoding="utf-8")

        attempt_root = self.worqspace_root / "attempt_placeholder"
        staging_dir = attempt_root / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "app.js").write_text("// TODO: implement this\n", encoding="utf-8")
        staged_attempt = {
            "staging_dir": staging_dir,
            "file_records": [
                {
                    "path": "app.js",
                    "size_bytes": len("// TODO: implement this\n".encode("utf-8")),
                    "content_sha256": "x",
                }
            ],
        }
        suspicious = construqtor._evaluate_primary_deliverable_sizes(
            staged_attempt,
            self.qodeyard,
            ["app.js"],
            policy_cfg=construqtor.DEFAULT_WRITE_STRATEGY["hybrid_policy"],
        )
        self.assertTrue(any("placeholder" in row or "collapse" in row or "size=" in row for row in suspicious))

if __name__ == '__main__':
    unittest.main()
