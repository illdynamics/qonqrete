import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORQER_DIR = ROOT / "worqer"
if str(WORQER_DIR) not in sys.path:
    sys.path.insert(0, str(WORQER_DIR))

import calqulator  # noqa: E402


class CalqulatorDefaultsTests(unittest.TestCase):
    def test_default_target_is_gemini(self):
        provider, model = calqulator.resolve_calqulator_target({})
        self.assertEqual(provider, "gemini")
        self.assertEqual(model, "gemini-2.5-flash-lite")

    def test_explicit_calqulator_override_wins(self):
        cfg = {
            "agents": {
                "calqulator": {"provider": "openai", "model": "gpt-4.1"},
                "construqtor": {"provider": "venice", "model": "deepseek-v3.2"},
            }
        }
        provider, model = calqulator.resolve_calqulator_target(cfg)
        self.assertEqual(provider, "openai")
        self.assertEqual(model, "gpt-4.1")

    def test_legacy_local_calqulator_config_falls_back_to_construqtor(self):
        cfg = {
            "agents": {
                "calqulator": {"provider": "local", "model": "calqulator"},
                "construqtor": {"provider": "gemini", "model": "gemini-2.5-flash"},
            }
        }
        provider, model = calqulator.resolve_calqulator_target(cfg)
        self.assertEqual(provider, "gemini")
        self.assertEqual(model, "gemini-2.5-flash")

    def test_legacy_local_calqulator_without_construqtor_is_still_gemini_default(self):
        cfg = {
            "agents": {
                "calqulator": {"provider": "local", "model": "calqulator"},
            }
        }
        provider, model = calqulator.resolve_calqulator_target(cfg)
        self.assertEqual(provider, "gemini")
        self.assertEqual(model, "gemini-2.5-flash-lite")


class LauncherNoSyncSemanticsTests(unittest.TestCase):
    def _prepare_run_exports_block(self) -> str:
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        start = shell_text.index("prepare_run_exports() {")
        end = shell_text.index("\nfinalize_run_session() {", start)
        return shell_text[start:end]

    def _finalize_run_session_block(self) -> str:
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        start = shell_text.index("finalize_run_session() {")
        end = shell_text.index("\nclean_repo_outputs() {", start)
        return shell_text[start:end]

    def test_no_sync_skips_repo_sync_only(self):
        block = self._finalize_run_session_block()
        self.assertIn('sync_repo_outputs_from_qage "$run_host_path"', block)
        self.assertIn("Repo-native export skipped by --no-sync; outputs remain in Qage/Qonstruction paths.", block)

    def test_no_sync_path_keeps_qage_output_flow(self):
        block = self._finalize_run_session_block()
        self.assertIn('save_qonstruction_non_interactive "$run_host_path" "$QONSTRUCTION_NAME"', block)
        self.assertIn('prompt_save_qonstruction "$run_host_path"', block)
        self.assertNotIn("delete_qage", block)

    def test_run_container_exit_status_is_preserved_after_finalize(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn('run_container "$RUN_HOST_PATH" || run_exit=$?', shell_text)
        self.assertIn('finalize_run_session "$RUN_HOST_PATH"', shell_text)
        self.assertIn('exit "$run_exit"', shell_text)

    def test_prepare_run_exports_records_sync_mode_lineage(self):
        block = self._prepare_run_exports_block()
        self.assertIn('export QONQ_REPO_SYNC_MODE="sync_to_repo_root"', block)
        self.assertIn('export QONQ_REPO_SYNC_MODE="no_sync"', block)


class LauncherEngineSemanticsTests(unittest.TestCase):
    def test_explicit_engine_requests_are_handled(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn('case "${CONTAINER_ENGINE:-}" in', shell_text)
        self.assertIn("docker)", shell_text)
        self.assertIn("podman)", shell_text)
        self.assertIn("command -v docker", shell_text)
        self.assertIn("command -v podman", shell_text)

    def test_explicit_container_engine_none_requires_unsafe_host_opt_in(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        start = shell_text.index("detect_engine() {")
        end = shell_text.index("\ndetect_build_backend() {", start)
        block = shell_text[start:end]
        self.assertIn('none)', block)
        self.assertIn('${QONQ_UNSAFE_HOST_MODE:-}" != "1"', block)
        self.assertIn("CONTAINER_ENGINE=none requires explicit host execution opt-in", block)
        self.assertIn("CONTAINER_ENGINE=none and QONQ_UNSAFE_HOST_MODE=1", block)

    def test_codeseeq_host_mode_inherits_host_execution_context(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        start = shell_text.index("detect_engine() {")
        end = shell_text.index("\ndetect_build_backend() {", start)
        block = shell_text[start:end]
        self.assertIn('is_truthy_env "${CODESEEQ_HOST_MODE:-}"', block)
        self.assertIn('CONTAINER_ENGINE="none"', block)
        self.assertIn('export QONQ_UNSAFE_HOST_MODE=1', block)
        self.assertIn("codeseeq provider stays executable", block)

    def test_parent_codeseeq_host_mode_survives_repo_env_loading(self):
        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn("CODESEEQ_HOST_MODE_FROM_PARENT", shell_text)
        self.assertIn("load_repo_env", shell_text)
        self.assertIn('export CODESEEQ_HOST_MODE="$CODESEEQ_HOST_MODE_FROM_PARENT"', shell_text)


if __name__ == "__main__":
    unittest.main()
