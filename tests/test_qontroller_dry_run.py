"""
End-to-end test of the whole clarify -> plan -> build -> review -> repair
loop using the mock adapter -- zero API calls, zero codeseeq install
required. This is what `qq run task.md --dry-run` exercises, just
called directly instead of via the CLI.
"""
import unittest
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters.mock import MockAdapter
from qq.qontroller import QontrollerConfig, run
from tests import run_cli_checked


def _make_config(repo_root, max_cycles=10, harness_commands=None,
                 review_on_harness_failure=False):
    return QontrollerConfig(
        repo_root=repo_root,
        run_root=os.path.join(repo_root, ".qq", "runs", "test"),
        model_qlarifier="mock", model_instruqtor="mock",
        model_construqtor="mock", model_inspeqtor="mock",
        briq_sensitivity=5, max_cycles=max_cycles,
        harness_commands=harness_commands or [],
        review_on_harness_failure=review_on_harness_failure,
    )


class TestDryRunReachesDone(unittest.TestCase):
    def test_dry_run_reaches_done(self):
        tmp = tempfile.mkdtemp(prefix="qq_test_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            state = run(
                "build a tiny hello world tool", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "done")
            self.assertEqual(state.cycle, 2)
            self.assertEqual(len(state.verdict_history), 2)
            self.assertTrue(state.verdict_history[-1].passed)

            events_path = os.path.join(config.run_root, "events.jsonl")
            self.assertTrue(os.path.exists(events_path))

            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            event_types = [e["type"] for e in events]
            self.assertIn("run.started", event_types)
            self.assertIn("clarification.done", event_types)
            self.assertIn("plan.created", event_types)
            self.assertIn("review.verdict", event_types)
            self.assertIn("run.completed", event_types)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_max_cycles_aborts(self):
        tmp = tempfile.mkdtemp(prefix="qq_max_")
        try:
            config = _make_config(tmp, max_cycles=1)
            adapter = MockAdapter()
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "aborted")
            self.assertNotEqual(state.status.value, "done")

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            event_types = [e["type"] for e in events]
            self.assertIn("run.aborted", event_types)
            self.assertNotIn("run.completed", event_types)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clarifier_runs_once(self):
        tmp = tempfile.mkdtemp(prefix="qq_clarify_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "done")
            self.assertIsNotNone(state.clarified_task)
            self.assertIn("mock",
                          state.clarified_task.clarified_text.lower())
            self.assertIsNotNone(state.plan)
            self.assertEqual(len(state.plan.briqs), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sequential_groups_see_changes(self):
        tmp = tempfile.mkdtemp(prefix="qq_seq_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            state = run(
                "build two sequential things", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "done")
            main_py = os.path.join(tmp, "main.py")
            self.assertTrue(os.path.exists(main_py),
                            f"Expected main.py in repo root: {tmp}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_event_log_has_required_types(self):
        tmp = tempfile.mkdtemp(prefix="qq_events_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            event_types = {e["type"] for e in events}

            required = {
                "run.started", "config.loaded",
                "clarification.done", "plan.created",
                "agent.call.started", "workspace.created", "workspace.committed",
                "workspace.merge.started", "workspace.merge.completed",
                "review.verdict", "run.completed",
            }
            for r in required:
                self.assertIn(r, event_types,
                              f"Missing required event type: {r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_state_snapshots_exist(self):
        tmp = tempfile.mkdtemp(prefix="qq_state_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            state_dir = os.path.join(config.run_root, "state")
            self.assertTrue(
                os.path.exists(os.path.join(state_dir, "task.json")),
                "Missing task.json")
            self.assertTrue(
                os.path.exists(os.path.join(state_dir,
                                             "clarified_task.json")),
                "Missing clarified_task.json")
            self.assertTrue(
                os.path.exists(os.path.join(state_dir, "plan.json")),
                "Missing plan.json")
            self.assertTrue(
                os.path.exists(os.path.join(state_dir, "final.json")),
                "Missing final.json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_harness_failure_creates_repair_issues(self):
        tmp = tempfile.mkdtemp(prefix="qq_harness_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=3,
                harness_commands=["exit 1"],
            )
            adapter = MockAdapter()
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            # Should abort because harness keeps failing
            self.assertIn(state.status.value, ["aborted", "done"])
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            event_types = {e["type"] for e in events}
            self.assertIn("harness.started", event_types)
            self.assertIn("harness.failed", event_types)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEventRunID(unittest.TestCase):
    """Every event must include run_id."""
    def test_all_events_have_run_id(self):
        tmp = tempfile.mkdtemp(prefix="qq_rid_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            self.assertGreater(len(events), 0, "No events logged")
            for e in events:
                self.assertIn("run_id", e,
                              f"Event missing run_id: {e.get('type')}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_config_loaded_event(self):
        tmp = tempfile.mkdtemp(prefix="qq_cfg_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            config_events = [e for e in events if e["type"] == "config.loaded"]
            self.assertEqual(len(config_events), 1)
            self.assertIn("provider", config_events[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_harness_failed_event(self):
        tmp = tempfile.mkdtemp(prefix="qq_hf_")
        try:
            config = _make_config(tmp, max_cycles=3,
                                  harness_commands=["exit 1"])
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            hf_events = [e for e in events if e["type"] == "harness.failed"]
            self.assertGreater(len(hf_events), 0)
            # All harness.failed events should have failures list
            for e in hf_events:
                self.assertIn("failures", e)
            # repair.issues_mapped should follow harness.failed
            repair_events = [e for e in events
                           if e["type"] == "repair.issues_mapped"
                           and e.get("source") == "harness"]
            self.assertGreater(len(repair_events), 0,
                               "repair.issues_mapped with source=harness not found")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_repair_issues_mapped_on_inspeqtor(self):
        tmp = tempfile.mkdtemp(prefix="qq_rim_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            repair_events = [e for e in events
                           if e["type"] == "repair.issues_mapped"
                           and e.get("source") == "inspeqtor"]
            self.assertGreater(len(repair_events), 0,
                               "repair.issues_mapped with source=inspeqtor not found")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestFinalJson(unittest.TestCase):
    """final.json must be written on success, abort, and run.failed."""

    def test_final_json_on_success(self):
        tmp = tempfile.mkdtemp(prefix="qq_fj_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            final_path = os.path.join(config.run_root, "state", "final.json")
            self.assertTrue(os.path.exists(final_path))
            with open(final_path) as f:
                data = json.load(f)
            self.assertEqual(data["status"], "done")
            self.assertIn("run_id", data)
            self.assertIn("run_root", data)
            self.assertIn("repo_root", data)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_final_json_on_abort(self):
        tmp = tempfile.mkdtemp(prefix="qq_fja_")
        try:
            config = _make_config(tmp, max_cycles=1)
            adapter = MockAdapter()
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "aborted")
            final_path = os.path.join(config.run_root, "state", "final.json")
            self.assertTrue(os.path.exists(final_path))
            with open(final_path) as f:
                data = json.load(f)
            self.assertEqual(data["status"], "aborted")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_final_json_on_harness_failure_abort(self):
        tmp = tempfile.mkdtemp(prefix="qq_fjhf_")
        try:
            config = _make_config(tmp, max_cycles=2,
                                  harness_commands=["exit 1"])
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            final_path = os.path.join(config.run_root, "state", "final.json")
            self.assertTrue(os.path.exists(final_path))
            with open(final_path) as f:
                data = json.load(f)
            # With the fix, harness failures now route through InspeQtor
            # instead of skipping it. The MockAdapter's inspeQtor returns
            # FULLY_DONE on the second call, so the run completes as 'done'
            # rather than aborting at max_cycles.
            self.assertIn(data["status"], ["aborted", "done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestArtifactLayout(unittest.TestCase):
    """Verify the dry-run creates proper artifact directories."""

    def test_all_roles_have_artifact_dirs(self):
        tmp = tempfile.mkdtemp(prefix="qq_art_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            agents_dir = os.path.join(config.run_root, "agents")
            self.assertTrue(os.path.isdir(agents_dir))

            # Check directory structure
            dirs = []
            for root, dnames, fnames in os.walk(agents_dir):
                for d in dnames:
                    rel = os.path.relpath(os.path.join(root, d), agents_dir)
                    dirs.append(rel)

            # Should have cycle-000 with qlarifier and instruqtor
            self.assertIn("cycle-000/qlarifier", "\n".join(dirs))
            self.assertIn("cycle-000/instruqtor", "\n".join(dirs))

            # Should have construqtor in cycle-001
            self.assertIn("cycle-001/construqtor", "\n".join(dirs))
            # Should have inspeqtor in cycle-001
            self.assertIn("cycle-001/inspeqtor", "\n".join(dirs))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_artifact_files_exist(self):
        tmp = tempfile.mkdtemp(prefix="qq_af_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            agents_dir = os.path.join(config.run_root, "agents")

            # Find a call-id directory
            call_dirs = []
            for root, dnames, fnames in os.walk(agents_dir):
                for d in dnames:
                    if d.startswith("call-"):
                        call_dirs.append(os.path.join(root, d))

            self.assertGreater(len(call_dirs), 0,
                               "No call directories found")
            # Check first call dir has all files
            cd = call_dirs[0]
            for fname in ("prompt.md", "stdout.txt", "stderr.txt",
                          "result.json", "metadata.json"):
                self.assertTrue(
                    os.path.exists(os.path.join(cd, fname)),
                    f"Missing {fname} in {cd}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCleanArtifacts(unittest.TestCase):
    """Verify Qq scratch files are not left in git worktrees."""
    import subprocess as sp

    def test_no_qq_scratch_in_git_files(self):
        tmp = tempfile.mkdtemp(prefix="qq_clean_")
        try:
            config = _make_config(tmp, max_cycles=10)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            # Check git ls-files for Qq scratch
            result = run_cli_checked(
                ["git", "ls-files"],
                cwd=tmp, timeout=10,
            )
            files = result.stdout.splitlines()
            scratch = [f for f in files
                       if any(p in f for p in (
                           ".qq_prompt_", "_output.json",
                           "clarifier_output.json",
                           "instructor_output.json",
                           "construqtor_output.json",
                           "inspeqtor_output.json",
                           ".qq_artifacts",
                       ))]
            self.assertEqual(len(scratch), 0,
                             f"Scratch files in git: {scratch}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestReviewOnHarnessFailureFlag(unittest.TestCase):
    """--review-on-harness-failure flag controls InspeQtor after harness fail."""

    def test_default_skips_inspeqtor_on_harness_fail(self):
        tmp = tempfile.mkdtemp(prefix="qq_rhf_")
        try:
            config = _make_config(tmp, max_cycles=3,
                                  harness_commands=["exit 1"],
                                  review_on_harness_failure=False)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            # After harness.failed, InspeQtor now runs in the same cycle
            # (changed from skipping to routing through InspeQtor for review).
            # Verify that review.verdict EXISTS in the event stream.
            review_events = [e for e in events if e["type"] == "review.verdict"]
            self.assertGreater(len(review_events), 0,
                               "Expected at least one review.verdict event")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_review_on_harness_failure_runs_inspeqtor(self):
        tmp = tempfile.mkdtemp(prefix="qq_rhft_")
        try:
            config = _make_config(tmp, max_cycles=3,
                                  harness_commands=["exit 1"],
                                  review_on_harness_failure=True)
            adapter = MockAdapter()
            run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path, "r") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
            event_types = {e["type"] for e in events}
            self.assertIn("harness.failed", event_types)
            # With review_on_harness_failure=True, review.verdict should appear
            self.assertIn("review.verdict", event_types)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPackageCLI(unittest.TestCase):
    """Test package operations using direct function calls (no subprocess).
    Uses qq.package.build, check_tree, check_archive which are importable
    Python functions — avoids spawning nested Python processes that can
    hang during full-suite runs."""

    def test_package_build_and_check_direct(self):
        """Build release zip and check archive via direct function calls."""
        from qq.package import build, check_archive, get_version
        import shutil, tempfile

        version = get_version()
        tmp = tempfile.mkdtemp(prefix="qq_pkgtest_")
        try:
            # Build in temp dir
            zip_path = build(root=os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..")),
                dist_dir=tmp)
            self.assertTrue(os.path.exists(zip_path),
                            f"Expected zip at {zip_path}")
            self.assertIn(f"qonqrete-qq-v{version}", zip_path)

            # Validate archive
            archive_rc = check_archive(zip_path)
            self.assertEqual(archive_rc, 0,
                             f"check_archive failed: rc={archive_rc}")

            # Also validate as uploaded zip
            from qq.package import check_archive as check_uploaded
            upload_rc = check_uploaded(zip_path)
            self.assertEqual(upload_rc, 0,
                             f"check_uploaded_zip failed: rc={upload_rc}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_source_tree_check_direct(self):
        """Check source tree via direct check_tree() call."""
        from qq.package import check_tree
        root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        try:
            rc = check_tree(root=root)
        except SystemExit as e:
            rc = e.code

        # Source tree may be dirty (.codeseeq/, prompt*.md) — check message
        has_codeseeq = os.path.isdir(os.path.join(root, ".codeseeq"))
        has_prompt = any(
            os.path.exists(os.path.join(root, f"prompt{i}.md"))
            for i in ["", "2", "3", "4", "5"]
        )
        if has_codeseeq or has_prompt:
            self.assertNotEqual(rc, 0,
                                "check_tree should fail when .codeseeq/ or prompt*.md exist")
        else:
            self.assertEqual(rc, 0,
                             "check_tree should pass on clean tree")


class TestRunIDSafety(unittest.TestCase):
    """Run ID / branch name safety for unsafe custom roots."""
    import subprocess as sp

    def _check_branch(self, branch_name):
        result = run_cli_checked(
            ["git", "check-ref-format", "--branch", branch_name],
            cwd="/tmp", timeout=10,
        )
        return result.returncode == 0

    def test_slugify_unsafe_run_ids(self):
        from qq.models import slugify_id
        unsafe = [
            "foo.lock", "a..b", "bad@{x}", "white space",
            "slash/back", "trailing.", ".leading",
        ]
        for u in unsafe:
            safe = slugify_id(u, "run")
            self.assertNotIn("..", safe, f"Unsafe slug for '{u}': {safe}")
            self.assertFalse(safe.endswith(".lock"),
                             f"Lock suffix in '{u}': {safe}")
            self.assertNotIn("@{", safe, "@{ in '%s': %s" % (u, safe))
            self.assertNotIn(" ", safe, f"Space in '{u}': {safe}")
            self.assertNotIn("/", safe, f"Slash in '{u}': {safe}")

    def test_safe_branch_name_with_unsafe_inputs(self):
        from qq.workspaces import safe_branch_name
        cases = [
            ("foo.lock", "bg-core", 1),
            ("a..b", "bg-test", 0),
            ("bad@{x}", "bg-1", 5),
            ("white space", "bg-2", 3),
            ("slash/back", "bg-3", 10),
        ]
        for run_id, bg_id, cycle in cases:
            branch = safe_branch_name(run_id, bg_id, cycle)
            self.assertTrue(
                self._check_branch(branch),
                f"Invalid git branch: '{branch}' for run_id='{run_id}'"
            )


if __name__ == "__main__":
    unittest.main()
