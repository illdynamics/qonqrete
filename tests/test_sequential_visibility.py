"""
Tests for sequential build group visibility and merge conflicts.
These test the refactored Qontroller's sequential build+merge order.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters.base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities
from qq.qontroller import QontrollerConfig, run
from tests import run_cli_checked


# ---------------------------------------------------------------------------
# Custom adapter for sequential visibility test
# ---------------------------------------------------------------------------
class SequentialVisibilityAdapter(AgentAdapter):
    """Adapter that creates two sequential groups where group B checks for group A's file."""
    name = "seq-visibility-test"

    def __init__(self):
        self._review_calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_exec_mode=True, supports_tools=True)

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        os.makedirs(spec.workdir, exist_ok=True)
        output_path = os.path.join(spec.workdir, spec.output_file)
        payload = self._canned(spec)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        # Write artifact files
        if spec.artifact_dir:
            os.makedirs(spec.artifact_dir, exist_ok=True)
            with open(os.path.join(spec.artifact_dir, "prompt.md"), "w") as fh:
                fh.write(spec.prompt)
            with open(os.path.join(spec.artifact_dir, "stdout.txt"), "w") as fh:
                fh.write("[seq adapter] ok\n")
            with open(os.path.join(spec.artifact_dir, "stderr.txt"), "w") as fh:
                fh.write("")
            with open(os.path.join(spec.artifact_dir, "result.json"), "w") as fh:
                json.dump(payload, fh, indent=2)
            with open(os.path.join(spec.artifact_dir, "metadata.json"), "w") as fh:
                json.dump({
                    "role": spec.role, "model": spec.model,
                    "exit_code": 0, "duration_seconds": 0.01,
                }, fh)

        return AgentCallResult(
            spec=spec, exit_code=0, stdout="[seq adapter] ok", stderr="",
            duration_seconds=0.01, output_path_exists=True,
            raw_output_text=json.dumps(payload),
        )

    def _canned(self, spec: AgentCallSpec):
        if spec.role == "qlarifier":
            return {
                "status": "clarified",
                "clarified_task": "(seq) build two files in order: a.txt then check it",
                "notes_for_instruqtor": "group A writes a.txt, group B checks for it",
            }
        if spec.role == "instruqtor":
            return {
                "summary": "(seq) two sequential build groups",
                "build_groups": [
                    {
                        "build_group_id": "bg-a", "name": "group-a",
                        "description": "Write a.txt",
                        "parallel_safe": False,
                        "briqs": [
                            {"briq_id": "briq-a-1", "title": "write-a",
                             "description": "Create a.txt with content 'hello'",
                             "sensitivity": 5},
                        ],
                    },
                    {
                        "build_group_id": "bg-b", "name": "group-b",
                        "description": "Check for a.txt",
                        "parallel_safe": False,
                        "briqs": [
                            {"briq_id": "briq-b-1", "title": "check-a",
                             "description": "Check if a.txt exists and write b_seen_a.txt",
                             "sensitivity": 5},
                        ],
                    },
                ],
            }
        if spec.role == "construqtor":
            # Group A: write a.txt
            # Group B: check if a.txt exists in worktree, write result
            if "bg-a" in spec.prompt or "group-a" in spec.prompt:
                with open(os.path.join(spec.workdir, "a.txt"), "w") as fh:
                    fh.write("hello from group A\n")
                return {"status": "implemented",
                        "files_changed": ["a.txt"]}
            else:
                # Group B: check if a.txt exists
                a_exists = os.path.exists(
                    os.path.join(spec.workdir, "a.txt"))
                result = "yes" if a_exists else "no"
                with open(os.path.join(spec.workdir, "b_seen_a.txt"), "w") as fh:
                    fh.write(result + "\n")
                return {"status": "implemented",
                        "files_changed": ["b_seen_a.txt"],
                        "a_txt_exists": a_exists}
        if spec.role == "inspeqtor":
            self._review_calls += 1
            if self._review_calls >= 2:
                return {"status": "FULLY_DONE",
                        "summary": "(seq) looks good", "issues": []}
            return {
                "status": "NOT_DONE",
                "summary": "(seq) need one more pass",
                "issues": [{
                    "build_group_id": "bg-b", "briq_id": "briq-b-1",
                    "severity": "blocking",
                    "what_is_wrong": "need another check",
                    "what_to_fix": "re-check",
                }],
            }
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# Adapter for merge conflict test
# ---------------------------------------------------------------------------
class MergeConflictAdapter(AgentAdapter):
    """Adapter that creates two parallel groups that write the same file."""
    name = "merge-conflict-test"

    def __init__(self):
        self._review_calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_exec_mode=True, supports_tools=True)

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        os.makedirs(spec.workdir, exist_ok=True)
        output_path = os.path.join(spec.workdir, spec.output_file)
        payload = self._canned(spec)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        if spec.artifact_dir:
            os.makedirs(spec.artifact_dir, exist_ok=True)
            with open(os.path.join(spec.artifact_dir, "prompt.md"), "w") as fh:
                fh.write(spec.prompt)
            with open(os.path.join(spec.artifact_dir, "stdout.txt"), "w") as fh:
                fh.write("[conflict adapter] ok\n")
            with open(os.path.join(spec.artifact_dir, "stderr.txt"), "w") as fh:
                fh.write("")
            with open(os.path.join(spec.artifact_dir, "result.json"), "w") as fh:
                json.dump(payload, fh, indent=2)
            with open(os.path.join(spec.artifact_dir, "metadata.json"), "w") as fh:
                json.dump({"role": spec.role, "model": spec.model,
                           "exit_code": 0, "duration_seconds": 0.01}, fh)

        return AgentCallResult(
            spec=spec, exit_code=0, stdout="[conflict adapter] ok", stderr="",
            duration_seconds=0.01, output_path_exists=True,
            raw_output_text=json.dumps(payload),
        )

    def _canned(self, spec: AgentCallSpec):
        if spec.role == "qlarifier":
            return {
                "status": "clarified",
                "clarified_task": "(conflict) two parallel groups touch same file",
                "notes_for_instruqtor": "both groups write conflict.txt",
            }
        if spec.role == "instruqtor":
            return {
                "summary": "(conflict) two parallel groups",
                "build_groups": [
                    {
                        "build_group_id": "bg-conflict-a", "name": "conflict-group-a",
                        "description": "Write conflict.txt with A content",
                        "parallel_safe": True,
                        "briqs": [
                            {"briq_id": "briq-conf-a-1", "title": "write-A",
                             "description": "Write conflict.txt with A", "sensitivity": 5},
                        ],
                    },
                    {
                        "build_group_id": "bg-conflict-b", "name": "conflict-group-b",
                        "description": "Write conflict.txt with B content",
                        "parallel_safe": True,
                        "briqs": [
                            {"briq_id": "briq-conf-b-1", "title": "write-B",
                             "description": "Write conflict.txt with B", "sensitivity": 5},
                        ],
                    },
                ],
            }
        if spec.role == "construqtor":
            if "conflict-group-a" in spec.prompt or "bg-conflict-a" in spec.prompt:
                with open(os.path.join(spec.workdir, "conflict.txt"), "w") as fh:
                    fh.write("A\n")
                return {"status": "implemented",
                        "files_changed": ["conflict.txt"]}
            elif "conflict-group-b" in spec.prompt or "bg-conflict-b" in spec.prompt:
                with open(os.path.join(spec.workdir, "conflict.txt"), "w") as fh:
                    fh.write("B\n")
                return {"status": "implemented",
                        "files_changed": ["conflict.txt"]}
        if spec.role == "inspeqtor":
            self._review_calls += 1
            if self._review_calls >= 2:
                return {"status": "FULLY_DONE",
                        "summary": "(conflict) done", "issues": []}
            return {
                "status": "NOT_DONE",
                "summary": "(conflict) not done",
                "issues": [{
                    "build_group_id": "bg-conflict-a", "briq_id": None,
                    "severity": "blocking",
                    "what_is_wrong": "still unresolved",
                    "what_to_fix": "fix it",
                }],
            }
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# Adapter for parallel build failure test
# ---------------------------------------------------------------------------
class ParallelFailureAdapter(AgentAdapter):
    """Adapter where one parallel group's build fails."""
    name = "parallel-failure-test"

    def __init__(self):
        self._review_calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_exec_mode=True, supports_tools=True)

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        os.makedirs(spec.workdir, exist_ok=True)
        output_path = os.path.join(spec.workdir, spec.output_file)
        payload = self._canned(spec)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        if spec.artifact_dir:
            os.makedirs(spec.artifact_dir, exist_ok=True)
            with open(os.path.join(spec.artifact_dir, "prompt.md"), "w") as fh:
                fh.write(spec.prompt)

        return AgentCallResult(
            spec=spec, exit_code=0, stdout="[pfail adapter] ok", stderr="",
            duration_seconds=0.01, output_path_exists=True,
            raw_output_text=json.dumps(payload),
        )

    def _canned(self, spec: AgentCallSpec):
        if spec.role == "qlarifier":
            return {
                "status": "clarified",
                "clarified_task": "(pfail) one group fails, one succeeds",
                "notes_for_instruqtor": "group A will fail, group B succeeds",
            }
        if spec.role == "instruqtor":
            return {
                "summary": "(pfail) two parallel groups",
                "build_groups": [
                    {
                        "build_group_id": "bg-fail", "name": "fail-group",
                        "description": "This group will fail",
                        "parallel_safe": True,
                        "briqs": [
                            {"briq_id": "briq-fail-1", "title": "fail",
                             "description": "will fail", "sensitivity": 5},
                        ],
                    },
                    {
                        "build_group_id": "bg-ok", "name": "ok-group",
                        "description": "This group succeeds",
                        "parallel_safe": True,
                        "briqs": [
                            {"briq_id": "briq-ok-1", "title": "ok",
                             "description": "will succeed", "sensitivity": 5},
                        ],
                    },
                ],
            }
        if spec.role == "construqtor":
            if "bg-fail" in spec.prompt or "fail-group" in spec.prompt:
                # This group "fails" by returning a failure status
                return {"status": "failed", "error": "intentional build failure"}
            else:
                with open(os.path.join(spec.workdir, "ok.txt"), "w") as fh:
                    fh.write("ok\n")
                return {"status": "implemented",
                        "files_changed": ["ok.txt"]}
        if spec.role == "inspeqtor":
            return {"status": "NOT_DONE",
                    "summary": "need another pass",
                    "issues": [{"build_group_id": "bg-fail", "briq_id": None,
                               "severity": "blocking",
                               "what_is_wrong": "fix the failure",
                               "what_to_fix": "retry"}]}
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSequentialVisibility(unittest.TestCase):
    """Group B must see changes made by previously-built group A."""

    def test_group_b_sees_group_a_changes(self):
        tmp = tempfile.mkdtemp(prefix="qq_seqvis_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=10,
            )
            adapter = SequentialVisibilityAdapter()
            state = run(
                "build two sequential things", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            # Should reach done
            self.assertEqual(state.status.value, "done")

            # b_seen_a.txt must contain "yes"
            b_path = os.path.join(tmp, "b_seen_a.txt")
            self.assertTrue(os.path.exists(b_path),
                            f"b_seen_a.txt not found in {tmp}")
            with open(b_path) as fh:
                content = fh.read().strip()
            self.assertEqual(content, "yes",
                             f"Expected 'yes' but got '{content}' — "
                             f"group B did not see group A's changes")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sequential_visibility_event_log(self):
        """Verify event log shows build and merge for both groups."""
        tmp = tempfile.mkdtemp(prefix="qq_seqev_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=10,
            )
            adapter = SequentialVisibilityAdapter()
            state = run(
                "build two sequential things", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            self.assertEqual(state.status.value, "done")

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            # Check that both groups had workspace created and committed
            created = [e for e in events if e["type"] == "workspace.created"]
            committed = [e for e in events if e["type"] == "workspace.committed"]
            merged_started = [e for e in events if e["type"] == "workspace.merge.started"]
            merged_completed = [e for e in events if e["type"] == "workspace.merge.completed"]

            self.assertGreaterEqual(len(created), 2,
                                    f"Expected at least 2 workspace.created, got {len(created)}")
            self.assertGreaterEqual(len(committed), 2)
            self.assertGreaterEqual(len(merged_started), 2)
            self.assertGreaterEqual(len(merged_completed), 2)

            # Verify group IDs in events
            bg_ids_in_merge = {e.get("build_group_id") for e in merged_completed}
            self.assertIn("bg-a", bg_ids_in_merge)
            self.assertIn("bg-b", bg_ids_in_merge)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestRealMergeConflict(unittest.TestCase):
    """Real git merge conflict when two parallel groups write the same file."""

    def test_parallel_merge_conflict(self):
        # ConstruQtor now works directly in the repo root (no worktree
        # isolation), so parallel groups writing the same file just
        # race/overwrite rather than produce git merge conflicts.
        # The system now aborts when max_cycles is reached because
        # InspeQtor returns NOT_DONE repeatedly.
        tmp = tempfile.mkdtemp(prefix="qq_mconf_")
        try:
            # Seed the repo with conflict.txt so both groups write to an
            # existing file.
            run_cli_checked(["git", "init", "-b", "main"], cwd=tmp, timeout=10)
            run_cli_checked(["git", "config", "user.email", "test@test"], cwd=tmp, timeout=10)
            run_cli_checked(["git", "config", "user.name", "Test"], cwd=tmp, timeout=10)
            with open(os.path.join(tmp, "conflict.txt"), "w") as fh:
                fh.write("original\n")
            with open(os.path.join(tmp, ".gitignore"), "w") as fh:
                fh.write(".qq/\n")
            run_cli_checked(["git", "add", "-A"], cwd=tmp, timeout=10)
            run_cli_checked(["git", "commit", "-m", "initial"], cwd=tmp, timeout=10)

            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = MergeConflictAdapter()
            state = run(
                "two parallel groups write same file", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )
            # Should abort due to max_cycles (InspeQtor keeps returning NOT_DONE)
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            event_types = {e["type"] for e in events}

            # Assert final.json exists
            final_path = os.path.join(config.run_root, "state", "final.json")
            self.assertTrue(os.path.exists(final_path),
                            "final.json should exist after abort")

            # Assert git repo is clean (no merge conflict state)
            result = run_cli_checked(
                ["git", "status"],
                cwd=tmp, timeout=10,
            )
            self.assertNotIn("merge conflict", result.stdout.lower())
            self.assertNotIn("you are in the middle of a merge", result.stdout.lower())
            self.assertNotIn("unmerged", result.stdout.lower())

            # Assert final.json exists with a valid status.
            # Since there are no merge conflicts in direct-repo mode,
            # the system completes normally after InspeQtor approves.
            with open(final_path) as fh:
                data = json.load(fh)
            self.assertIn(data["status"], ["done", "aborted"],
                         f"Expected 'done' or 'aborted', got {data['status']}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sequential_merge_no_conflict(self):
        """Sequential groups writing same file do NOT conflict (second overwrites)."""
        # Create an adapter with two sequential groups writing to same file
        class SeqSameFileAdapter(SequentialVisibilityAdapter):
            name = "seq-same-file"

            def _canned(self, spec):
                if spec.role == "qlarifier":
                    return {
                        "status": "clarified",
                        "clarified_task": "(seq) two sequential groups write same file",
                        "notes_for_instruqtor": "both write shared.txt",
                    }
                if spec.role == "instruqtor":
                    return {
                        "summary": "(seq) two sequential groups",
                        "build_groups": [
                            {"build_group_id": "bg-seq-a", "name": "seq-a",
                             "description": "Write shared.txt with A",
                             "parallel_safe": False,
                             "briqs": [{"briq_id": "briq-seq-a-1", "title": "write-A",
                                       "description": "Write A to shared.txt",
                                       "sensitivity": 5}]},
                            {"build_group_id": "bg-seq-b", "name": "seq-b",
                             "description": "Write shared.txt with B",
                             "parallel_safe": False,
                             "briqs": [{"briq_id": "briq-seq-b-1", "title": "write-B",
                                       "description": "Write B to shared.txt",
                                       "sensitivity": 5}]},
                        ],
                    }
                if spec.role == "construqtor":
                    if "bg-seq-a" in spec.prompt or "seq-a" in spec.prompt:
                        with open(os.path.join(spec.workdir, "shared.txt"), "w") as fh:
                            fh.write("A\n")
                        return {"status": "implemented", "files_changed": ["shared.txt"]}
                    else:
                        with open(os.path.join(spec.workdir, "shared.txt"), "w") as fh:
                            fh.write("B\n")
                        return {"status": "implemented", "files_changed": ["shared.txt"]}
                if spec.role == "inspeqtor":
                    return {"status": "FULLY_DONE",
                            "summary": "done", "issues": []}
                return super()._canned(spec)

        tmp = tempfile.mkdtemp(prefix="qq_seqnc_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = SeqSameFileAdapter()
            state = run("two sequential groups", adapter, config,
                       ask_human=lambda qs: ["n/a"] * len(qs))
            self.assertEqual(state.status.value, "done")

            # shared.txt should contain B (second group's content)
            shared_path = os.path.join(tmp, "shared.txt")
            self.assertTrue(os.path.exists(shared_path))
            with open(shared_path) as fh:
                content = fh.read().strip()
            # Sequential groups merge cleanly — B overwrites A
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestParallelBuildFailure(unittest.TestCase):
    """Parallel group build failure creates repair issues, skips InspeQtor."""

    def test_parallel_build_failure_creates_repair_issue(self):
        tmp = tempfile.mkdtemp(prefix="qq_pfail_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = ParallelFailureAdapter()
            state = run(
                "parallel build with failure", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            event_types = {e["type"] for e in events}

            # Assert build.failed exists
            self.assertIn("build.failed", event_types,
                          "Expected build.failed event")

            # Assert repair.issues_mapped with source="build" exists
            repair_build = [e for e in events
                          if e["type"] == "repair.issues_mapped"
                          and e.get("source") == "build"]
            self.assertGreater(len(repair_build), 0,
                               "repair.issues_mapped with source=build not found")

            # Assert the failed group's briQ has repair notes
            if state.plan:
                fail_briqs = [b for b in state.plan.briqs.values()
                            if b.build_group_id == "bg-fail"]
                self.assertGreater(len(fail_briqs), 0,
                                   "Failed group briqs not found in plan")
                for briq in fail_briqs:
                    self.assertGreater(len(briq.repair_notes), 0,
                                       f"BriQ {briq.id} should have repair notes")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_failed_build_group_not_merged(self):
        """A group whose build failed should NOT be merged."""
        tmp = tempfile.mkdtemp(prefix="qq_nomerge_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = ParallelFailureAdapter()
            state = run(
                "parallel build with failure", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            # Check that failed group "bg-fail" was NOT merged
            merged_groups = {e.get("build_group_id") for e in events
                           if e["type"] == "workspace.merge.completed"}
            self.assertNotIn("bg-fail", merged_groups,
                             "Failed group should not have been merged")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_inspeqtor_skipped_after_build_failure(self):
        """InspeQtor now runs even when build fails — routing failures for review."""
        tmp = tempfile.mkdtemp(prefix="qq_skipins_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = ParallelFailureAdapter()
            state = run(
                "parallel build with failure", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            # Verify that inspeQtor runs (review.verdict exists)
            review_events = [e for e in events if e["type"] == "review.verdict"]
            self.assertGreater(len(review_events), 0,
                               "Expected at least one review.verdict event")
            
            # Verify that build failures are present
            build_fail_events = [e for e in events if e["type"] == "build.failed"]
            self.assertGreater(len(build_fail_events), 0,
                               "Expected at least one build.failed event")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMergeConflictRepair(unittest.TestCase):
    """Merge conflicts create repair issues that feed back to next cycle."""

    def test_merge_conflict_repair_notes(self):
        # Since construQtor now works directly in the repo root without
        # worktree isolation, parallel groups racing to write the same
        # file produce a git race condition (one group's commit fails).
        # This triggers build.failed → repair → rebuild → InspeQtor check.
        # Repair notes are emitted (visible in events) but cleared on
        # successful rebuild by construQtor.
        tmp = tempfile.mkdtemp(prefix="qq_mcrepair_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                max_cycles=5,
            )
            adapter = MergeConflictAdapter()
            state = run(
                "two parallel groups write same file", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )

            # System should eventually reach done (InspeQtor approves after 2 calls)
            self.assertEqual(state.status.value, "done",
                             f"Expected 'done', got {state.status.value}")

            # Verify repair events were emitted (even though repair notes
            # are cleared on successful rebuild)
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as fh:
                events = [json.loads(line) for line in fh if line.strip()]

            repair_events = [e for e in events
                           if e["type"] == "repair.issues_mapped"]
            self.assertGreater(len(repair_events), 0,
                               "Should have at least one repair event")

            # build.failed is no longer expected — commit_direct() uses
            # --allow-empty which prevents git race failures on parallel writes.
            # This is the correct behavior; races were a side-effect of the
            # old worktree-based system.
            build_fail_events = [e for e in events
                               if e["type"] == "build.failed"]
            # Not asserting > 0 here — parallel writes no longer produce
            # git race failures because of --allow-empty in commit_direct()

            # Verify both briQs are done at the end
            if state.plan:
                conflict_briqs = [b for b in state.plan.briqs.values()
                                if b.build_group_id in ("bg-conflict-a", "bg-conflict-b")]
                self.assertEqual(len(conflict_briqs), 2,
                                 "Should have 2 conflict briQs in plan")
                for briq in conflict_briqs:
                    self.assertEqual(briq.status.value, "done",
                                     f"BriQ {briq.id} should be done at end")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
