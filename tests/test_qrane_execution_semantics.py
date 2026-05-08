import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QRANE_DIR = ROOT / "qrane"
sys.path.insert(0, str(QRANE_DIR))

from execution_model import (  # noqa: E402
    ESTIMATE_MODE_ADVISORY,
    ESTIMATE_MODE_SCHEDULER,
    PASS_BUILD,
    PASS_REPAIR,
    RESUME_MODE_INTAKE_WAITING_FOR_INPUT,
    ExecutionState,
    decide_post_inspection,
    resolve_resume_decision,
    resolve_cycle_estimate_mode,
    resolve_execution_limits,
    start_next_pass,
)
from lib_qrane import (  # noqa: E402
    RUN_MANIFEST_FILE,
    create_manifest,
    determine_validation_mode,
    finalize_manifest,
    load_manifest,
    record_pass_state,
    write_inspection_bridge,
)
from qrane import PathManager, inspection_exit_is_recoverable, run_pre_construqtor_context_refresh, should_skip_agent  # noqa: E402


class ExecutionModelTests(unittest.TestCase):
    def test_qrane_runs_qontrabender_for_non_gemini(self):
        self.assertFalse(
            should_skip_agent(
                name="qontrabender",
                use_qompressor=True,
                use_qontextor=True,
                use_qontrabender=True,
                is_repair_pass=False,
                construqtor_provider="deepseek",
            )
        )

    def test_qrane_pre_construqtor_qontrabender_pipeline_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            for name in ("qodeyard", "bloq.d", "qontext.d", "qache.d", "struqture"):
                (workspace / name).mkdir(parents=True, exist_ok=True)
            calls = []

            def fake_run(name, cmd, prefix, color, log_path, env):
                calls.append((name, cmd))
                return True

            run_pre_construqtor_context_refresh(
                path_manager=PathManager(workspace),
                agent_module_dir=ROOT / "worqer",
                prefix="t",
                agent_colors={},
                run_agent_func=fake_run,
                env={},
                use_qompressor=True,
                use_qontextor=True,
                use_qontrabender=True,
                worqspace=workspace,
                cycle=2,
            )

            qontrabender_calls = [cmd for name, cmd in calls if name == "qontrabender"]
            self.assertEqual(len(qontrabender_calls), 1)
            self.assertEqual(qontrabender_calls[0][1:], [
                str(ROOT / "worqer" / "qontrabender.py"),
                str(workspace / "bloq.d"),
                str(workspace / "qodeyard"),
                str(workspace / "qontext.d"),
                str(workspace / "qache.d"),
            ])
            self.assertNotIn("--check", qontrabender_calls[0])

    def test_advisory_mode_no_repair_needed_stops_after_first_build(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 4, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        decision = decide_post_inspection(
            state,
            limits,
            {"status": "SUCCESS", "repair_required": False, "task_completed": True},
            {},
        )
        self.assertEqual(decision.action, "stop")
        self.assertEqual(decision.reason, "completed")
        self.assertEqual(state.global_iteration_index, 1)
        self.assertEqual(state.build_pass_index, 1)
        self.assertEqual(state.repair_pass_index, 0)

    def test_advisory_mode_repair_needed_keeps_build_count_stable(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 5, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        decision = decide_post_inspection(
            state,
            limits,
            {"status": "PARTIAL", "repair_required": True, "task_completed": False},
            {"same_run_repair_eligible": True},
        )
        self.assertEqual(decision.action, "run_repair")
        start_next_pass(state, PASS_REPAIR, decision.repairing_build_pass_index)
        self.assertEqual(state.global_iteration_index, 2)
        self.assertEqual(state.build_pass_index, 1)
        self.assertEqual(state.repair_pass_index, 1)
        self.assertEqual(state.repairing_build_pass_index, 1)

    def test_scheduler_mode_can_continue_with_later_build_pass(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 5, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 1}})
        state = ExecutionState(
            cycle_estimate_mode=ESTIMATE_MODE_SCHEDULER,
            estimated_build_passes=2,
            scheduled_build_pass_target=2,
        )
        start_next_pass(state, PASS_BUILD)
        decision = decide_post_inspection(
            state,
            limits,
            {"status": "PARTIAL", "repair_required": False, "task_completed": False},
            {},
        )
        self.assertEqual(decision.action, "run_build")
        self.assertEqual(decision.reason, "scheduler_continuation")

    def test_scheduler_mode_repair_then_followup_build(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 6, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(
            cycle_estimate_mode=ESTIMATE_MODE_SCHEDULER,
            estimated_build_passes=2,
            scheduled_build_pass_target=2,
        )
        start_next_pass(state, PASS_BUILD)
        first = decide_post_inspection(
            state,
            limits,
            {"status": "PARTIAL", "repair_required": True, "task_completed": False},
            {"same_run_repair_eligible": True},
        )
        self.assertEqual(first.action, "run_repair")
        start_next_pass(state, PASS_REPAIR, first.repairing_build_pass_index)
        second = decide_post_inspection(
            state,
            limits,
            {"status": "PARTIAL", "repair_required": False, "task_completed": False},
            {},
        )
        self.assertEqual(second.action, "run_build")
        start_next_pass(state, PASS_BUILD)
        self.assertEqual(state.global_iteration_index, 3)
        self.assertEqual(state.build_pass_index, 2)
        self.assertEqual(state.repair_pass_index, 0)

    def test_caps_have_distinct_stop_reasons(self):
        repair_limits = resolve_execution_limits({"options": {"max_total_iterations": 5, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 1}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        start_next_pass(state, PASS_REPAIR, 1)
        repair_decision = decide_post_inspection(
            state,
            repair_limits,
            {"status": "PARTIAL", "repair_required": True, "task_completed": False},
            {"same_run_repair_eligible": True},
        )
        self.assertEqual(repair_decision.action, "stop_partial")
        self.assertEqual(repair_decision.reason, "repair_cap_hit")

        build_limits = resolve_execution_limits({"options": {"max_total_iterations": 5, "max_build_passes": 1}, "repair": {"max_attempts_per_build_pass": 1}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_SCHEDULER, estimated_build_passes=2, scheduled_build_pass_target=2)
        start_next_pass(state, PASS_BUILD)
        build_decision = decide_post_inspection(
            state,
            build_limits,
            {"status": "PARTIAL", "repair_required": False, "task_completed": False},
            {},
        )
        self.assertEqual(build_decision.action, "stop_partial")
        self.assertEqual(build_decision.reason, "build_pass_cap_hit")

        total_limits = resolve_execution_limits({"options": {"max_total_iterations": 1, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        total_decision = decide_post_inspection(
            state,
            total_limits,
            {"status": "PARTIAL", "repair_required": True, "task_completed": False},
            {"same_run_repair_eligible": True},
        )
        self.assertEqual(total_decision.action, "stop_partial")
        self.assertEqual(total_decision.reason, "total_iteration_cap_hit")

    def test_missing_inspection_artifacts_stop_partially(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 4, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        decision = decide_post_inspection(state, limits, {}, {})
        self.assertEqual(decision.action, "stop_partial")
        self.assertEqual(decision.reason, "inspection_artifacts_missing")

    def test_hard_gate_pass_forces_stop_even_if_status_is_partial(self):
        limits = resolve_execution_limits({"options": {"max_total_iterations": 4, "max_build_passes": 3}, "repair": {"max_attempts_per_build_pass": 2}})
        state = ExecutionState(cycle_estimate_mode=ESTIMATE_MODE_ADVISORY)
        start_next_pass(state, PASS_BUILD)
        decision = decide_post_inspection(
            state,
            limits,
            {
                "status": "PARTIAL",
                "hard_gate_status": "PASS",
                "repair_needed": False,
                "task_completed": True,
            },
            {"same_run_repair_eligible": True},
        )
        self.assertEqual(decision.action, "stop")
        self.assertEqual(decision.reason, "completed")

    def test_limit_aliases_and_estimate_mode_defaults(self):
        limits = resolve_execution_limits({"options": {"auto_cycle_limit": 7}, "repair": {"max_attempts": 4}})
        self.assertEqual(limits.max_total_iterations, 7)
        self.assertEqual(limits.max_build_passes, 7)
        self.assertEqual(limits.max_attempts_per_build_pass, 4)
        self.assertEqual(resolve_cycle_estimate_mode({}), ESTIMATE_MODE_ADVISORY)
        self.assertEqual(resolve_cycle_estimate_mode({"options": {"cycle_estimate_mode": "scheduler"}}), ESTIMATE_MODE_SCHEDULER)

    def test_inspection_exit_recoverable_when_verdict_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            verdict_dir = workspace / "verdict"
            verdict_dir.mkdir(parents=True, exist_ok=True)
            (verdict_dir / "inspection-verdict.v1.json").write_text(
                json.dumps({"status": "FAILURE", "repair_required": True}),
                encoding="utf-8",
            )
            recovered, notes = inspection_exit_is_recoverable(workspace)
            self.assertTrue(recovered)
            self.assertTrue(any("inspection verdict artifact present" in note for note in notes))


class ResumeDecisionTests(unittest.TestCase):
    def test_clarification_blocked_resume_reenters_intake_semantics(self):
        manifest = {
            "run_status": "RUN_WAITING_FOR_INPUT",
            "lifecycle_state": "BLOCKED",
            "current_stage": "CLARIFICATION",
            "execution": {
                "state": {
                    "global_iteration_index": 1,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 1,
                    "repair_pass_index": 0,
                    "stop_reason": "clarification_waiting_for_input",
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, RESUME_MODE_INTAKE_WAITING_FOR_INPUT)
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_BUILD)

    def test_clarification_stop_reason_preserves_intake_resume_after_manifest_warmup(self):
        manifest = {
            "run_status": "RUN_ACTIVE",
            "lifecycle_state": "READY_FOR_CLARIFICATION",
            "current_stage": "INTAKE",
            "execution": {
                "state": {
                    "global_iteration_index": 1,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 1,
                    "repair_pass_index": 0,
                    "stop_reason": "clarification_waiting_for_input",
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, RESUME_MODE_INTAKE_WAITING_FOR_INPUT)
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_BUILD)

    def test_interrupted_repair_resume_restores_repair_semantics(self):
        manifest = {
            "run_status": "RUN_ACTIVE",
            "lifecycle_state": "REPAIRING",
            "execution": {
                "state": {
                    "global_iteration_index": 4,
                    "pass_kind": PASS_REPAIR,
                    "build_pass_index": 2,
                    "repair_pass_index": 2,
                    "repairing_build_pass_index": 2,
                    "pending_next_pass_kind": None,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "interrupted_active_pass")
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_REPAIR)
        self.assertEqual(decision.repairing_build_pass_index, 2)

    def test_interrupted_build_resume_restores_build_semantics(self):
        manifest = {
            "run_status": "RUN_ACTIVE",
            "lifecycle_state": "BUILDING",
            "execution": {
                "state": {
                    "global_iteration_index": 3,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 3,
                    "repair_pass_index": 0,
                    "pending_next_pass_kind": None,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "interrupted_active_pass")
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_BUILD)

    def test_real_resume_flow_interrupted_repair_prioritizes_resume_state(self):
        # Simulates the actual runtime flow where a fresh wrapper manifest is created
        # but the prior active state is explicitly preserved in resume_state.
        manifest = {
            "run_status": "RUN_CREATED",
            "lifecycle_state": "CREATED",
            "current_stage": "INTAKE",
            "execution": {
                "state": {
                    "global_iteration_index": 4,
                    "pass_kind": PASS_REPAIR,
                    "build_pass_index": 2,
                    "repair_pass_index": 2,
                    "repairing_build_pass_index": 2,
                    "pending_next_pass_kind": None,
                },
                "resume_state": {
                    "prior_run_status": "RUN_ACTIVE",
                    "prior_lifecycle_state": "REPAIRING",
                    "prior_current_stage": "REPAIR",
                    "pass_kind": PASS_REPAIR,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "interrupted_active_pass")
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_REPAIR)
        self.assertEqual(decision.repairing_build_pass_index, 2)
        
    def test_real_resume_flow_interrupted_build_prioritizes_resume_state(self):
        manifest = {
            "run_status": "RUN_CREATED",
            "lifecycle_state": "CREATED",
            "current_stage": "INTAKE",
            "execution": {
                "state": {
                    "global_iteration_index": 3,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 3,
                    "repair_pass_index": 0,
                    "pending_next_pass_kind": None,
                },
                "resume_state": {
                    "prior_run_status": "RUN_ACTIVE",
                    "prior_lifecycle_state": "BUILDING",
                    "prior_current_stage": "BUILD",
                    "pass_kind": PASS_BUILD,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "interrupted_active_pass")
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_BUILD)


    def test_queued_next_repair_pass_is_honored(self):
        manifest = {
            "run_status": "RUN_ACTIVE",
            "execution": {
                "state": {
                    "global_iteration_index": 2,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 2,
                    "repair_pass_index": 0,
                    "pending_next_pass_kind": PASS_REPAIR,
                    "pending_repairing_build_pass_index": 2,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "queued_next_pass")
        self.assertFalse(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_REPAIR)
        self.assertEqual(decision.repairing_build_pass_index, 2)

    def test_queued_next_build_pass_is_honored(self):
        manifest = {
            "run_status": "RUN_ACTIVE",
            "execution": {
                "state": {
                    "global_iteration_index": 2,
                    "pass_kind": PASS_BUILD,
                    "build_pass_index": 2,
                    "repair_pass_index": 0,
                    "pending_next_pass_kind": PASS_BUILD,
                    "pending_repairing_build_pass_index": None,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "queued_next_pass")
        self.assertFalse(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_BUILD)

    def test_legacy_manifest_without_run_status_prefers_conservative_resume(self):
        manifest = {
            "execution": {
                "state": {
                    "global_iteration_index": 5,
                    "pass_kind": PASS_REPAIR,
                    "build_pass_index": 2,
                    "repair_pass_index": 3,
                    "pending_next_pass_kind": None,
                }
            },
        }
        decision = resolve_resume_decision(manifest)
        self.assertEqual(decision.mode, "legacy_active_pass")
        self.assertTrue(decision.resume_active_pass)
        self.assertEqual(decision.next_pass_kind, PASS_REPAIR)


class ManifestResumeTests(unittest.TestCase):
    def test_resume_manifest_keeps_execution_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            prior = {
                "schema_version": "run-manifest.v1",
                "run_id": workspace.name,
                "execution": {
                    "state": {
                        "global_iteration_index": 3,
                        "pass_kind": PASS_REPAIR,
                        "build_pass_index": 2,
                        "repair_pass_index": 1,
                        "repairing_build_pass_index": 2,
                        "cycle_estimate_mode": ESTIMATE_MODE_SCHEDULER,
                        "estimated_build_passes": 3,
                        "scheduled_build_pass_target": 3,
                        "pending_next_pass_kind": PASS_REPAIR,
                        "pending_repairing_build_pass_index": 2,
                        "stop_reason": "repair_requires_linked_continuation",
                    }
                }
            }
            (workspace / RUN_MANIFEST_FILE).write_text(json.dumps(prior), encoding="utf-8")
            old = os.environ.get("QONQ_RUN_KIND")
            os.environ["QONQ_RUN_KIND"] = "resume"
            try:
                create_manifest(workspace)
            finally:
                if old is None:
                    os.environ.pop("QONQ_RUN_KIND", None)
                else:
                    os.environ["QONQ_RUN_KIND"] = old
            manifest = load_manifest(workspace)
            state = manifest["execution"]["state"]
            self.assertEqual(state["global_iteration_index"], 3)
            self.assertEqual(state["build_pass_index"], 2)
            self.assertEqual(state["repair_pass_index"], 1)
            self.assertEqual(state["pending_next_pass_kind"], PASS_REPAIR)
            self.assertEqual(manifest["execution"]["resume_state"]["global_iteration_index"], 3)

    def test_inspection_bridge_includes_execution_metadata_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            record_pass_state(
                workspace,
                global_iteration_index=9,
                pass_kind=PASS_REPAIR,
                build_pass_index=3,
                repair_pass_index=2,
                repairing_build_pass_index=3,
                cycle_estimate_mode=ESTIMATE_MODE_SCHEDULER,
                estimated_build_passes=5,
                scheduled_build_pass_target=4,
            )
            reqap_dir = workspace / "reqap.d"
            reqap_dir.mkdir(parents=True, exist_ok=True)
            (reqap_dir / "cyqle9_reqap.md").write_text("Assessment: FAILURE\n", encoding="utf-8")

            bridge_ref = write_inspection_bridge(workspace, 9)
            bridge_payload = json.loads((workspace / bridge_ref).read_text(encoding="utf-8"))

            for key in [
                "global_iteration_index",
                "pass_kind",
                "build_pass_index",
                "repair_pass_index",
                "repairing_build_pass_index",
                "cycle_estimate_mode",
                "estimated_build_passes",
                "scheduled_build_pass_target",
            ]:
                self.assertIn(key, bridge_payload)
            self.assertEqual(bridge_payload["global_iteration_index"], 9)
            self.assertEqual(bridge_payload["pass_kind"], PASS_REPAIR)
            self.assertEqual(bridge_payload["cycle_estimate_mode"], ESTIMATE_MODE_SCHEDULER)

    def test_manifest_lineage_captures_repo_sync_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            old_run_kind = os.environ.get("QONQ_RUN_KIND")
            old_sync_mode = os.environ.get("QONQ_REPO_SYNC_MODE")
            try:
                os.environ["QONQ_RUN_KIND"] = "run"
                os.environ.pop("QONQ_REPO_SYNC_MODE", None)
                create_manifest(workspace)
                manifest_default = load_manifest(workspace)
                self.assertEqual(manifest_default["lineage"]["repo_sync_mode"], "sync_to_repo_root")

                os.environ["QONQ_REPO_SYNC_MODE"] = "no_sync"
                create_manifest(workspace)
                manifest_no_sync = load_manifest(workspace)
                self.assertEqual(manifest_no_sync["lineage"]["repo_sync_mode"], "no_sync")
            finally:
                if old_run_kind is None:
                    os.environ.pop("QONQ_RUN_KIND", None)
                else:
                    os.environ["QONQ_RUN_KIND"] = old_run_kind
                if old_sync_mode is None:
                    os.environ.pop("QONQ_REPO_SYNC_MODE", None)
                else:
                    os.environ["QONQ_REPO_SYNC_MODE"] = old_sync_mode

    def test_finalize_manifest_blocked_uses_waiting_for_input_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            finalize_manifest(workspace, "blocked", "Waiting for clarification input.")
            manifest = load_manifest(workspace)
            self.assertEqual(manifest["lifecycle_state"], "BLOCKED")
            self.assertEqual(manifest["run_status"], "RUN_WAITING_FOR_INPUT")

    def test_docs_help_and_config_reference_pass_semantics(self):
        docs_text = (ROOT / "doc" / "DOCUMENTATION.md").read_text(encoding="utf-8")
        self.assertIn("max_build_passes", docs_text)
        self.assertIn("max_attempts_per_build_pass", docs_text)
        self.assertIn("interrupted active pass", docs_text.lower())
        self.assertIn("smoketest", docs_text.lower())
        self.assertIn("run_waiting_for_input", docs_text.lower())
        self.assertIn("clarification", docs_text.lower())

        help_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn("max_total_iterations", help_text)
        self.assertIn("max_build_passes", help_text)
        self.assertIn("--seed-repo", help_text)
        self.assertIn("Legacy alias for --seed-repo", help_text)
        self.assertIn("--no-sync", help_text)
        self.assertIn("Skip sync-back into repo root", help_text)
        self.assertIn("record_pre_run_visible_snapshot", help_text)
        self.assertIn("pre_run_visible_files.v1.json", help_text)

        config_text = (ROOT / "worqspace" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("same-run repairs consume max_total_iterations", config_text.lower())
        self.assertIn("smoketest", config_text.lower())

    def test_podman_linux_dev_mounts_keep_read_only_with_selinux_relabel(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn('local dev_mount_ro_suffix=":ro"', shell_text)
        self.assertIn('if [ "$CONTAINER_ENGINE" = "podman" ] && [ "$DETECTED_OS" = "Linux" ]; then', shell_text)
        self.assertIn('dev_mount_ro_suffix=":ro,z"', shell_text)
        self.assertIn('-v "${norm_script_dir}/qrane:/qonqrete/qrane${dev_mount_ro_suffix}"', shell_text)
        self.assertIn('-v "${norm_script_dir}/worqer:/qonqrete/worqer${dev_mount_ro_suffix}"', shell_text)

    def test_launcher_no_sync_wires_finalize_gate_and_default_sync(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn("SYNC_TO_REPO=true", shell_text)
        self.assertIn("-N|--no-sync)                    SYNC_TO_REPO=false; shift ;;", shell_text)
        self.assertIn("finalize_run_session()", shell_text)
        self.assertIn('if [ "$SYNC_TO_REPO" = true ]; then', shell_text)
        self.assertIn('sync_repo_outputs_from_qage "$run_host_path"', shell_text)
        self.assertIn("Repo-native export skipped by --no-sync", shell_text)

    def test_qrane_exits_nonzero_for_partial_failed_or_blocked_terminal_states(self):
        qrane_text = (ROOT / "qrane" / "qrane.py").read_text(encoding="utf-8")
        self.assertIn("if session_failed or partial_stop:", qrane_text)
        self.assertIn("final_exit_code = 1", qrane_text)
        self.assertIn("elif blocked_stop:", qrane_text)
        self.assertIn("final_exit_code = 2", qrane_text)
        self.assertIn("sys.exit(final_exit_code)", qrane_text)

    def test_determine_validation_mode_prefers_bundle_execution_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "validation").mkdir(parents=True, exist_ok=True)
            (workspace / "validation" / "validation-bundle.v1.json").write_text(
                json.dumps({"validation_execution_mode": "EXECUTED"}),
                encoding="utf-8",
            )
            self.assertEqual(determine_validation_mode(workspace), "EXECUTED")

            (workspace / "validation" / "validation-bundle.v1.json").write_text(
                json.dumps({"validation_execution_mode": "MIXED"}),
                encoding="utf-8",
            )
            self.assertEqual(determine_validation_mode(workspace), "MIXED")

    def test_determine_validation_mode_fallback_requires_explicit_smoke_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "reqap.d" / "cyqle3").mkdir(parents=True, exist_ok=True)
            (workspace / "reqap.d" / "cyqle3" / "cyqle3_smoketest.md").write_text("# smoke\n", encoding="utf-8")
            self.assertEqual(determine_validation_mode(workspace), "NONE")

            (workspace / "reqap.d" / "cyqle3" / "cyqle3_verification.md").write_text("verification\n", encoding="utf-8")
            self.assertEqual(determine_validation_mode(workspace), "STATIC_ONLY")

            (workspace / "reqap.d" / "cyqle3" / "cyqle3_smoketest.v1.json").write_text(
                json.dumps({"executed_count": 1, "static_count": 0, "results": []}),
                encoding="utf-8",
            )
            self.assertEqual(determine_validation_mode(workspace), "MIXED")

            (workspace / "reqap.d" / "cyqle3" / "cyqle3_verification.md").unlink()
            self.assertEqual(determine_validation_mode(workspace), "EXECUTED")

            (workspace / "reqap.d" / "cyqle3" / "cyqle3_smoketest.v1.json").unlink()
            (workspace / "reqap.d" / "cyqle3" / "cyqle3_smoketest.md").write_text(
                "- Executed Count: 0\n- Static Count: 2\n",
                encoding="utf-8",
            )
            self.assertEqual(determine_validation_mode(workspace), "STATIC_ONLY")


if __name__ == "__main__":
    unittest.main()
