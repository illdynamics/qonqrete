"""Tests for config loading and validation."""
import unittest
import sys
import os
import tempfile
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.config import resolve_config, load_providers, QqConfig


def _write_qq_yaml(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestProviders(unittest.TestCase):
    def test_load_providers(self):
        providers = load_providers()
        self.assertIn("codeseeq", providers)
        self.assertIn("mock", providers)
        csq = providers["codeseeq"]
        self.assertEqual(csq.status, "implemented")
        self.assertIn("deepseek-v4-flash", csq.models)
        self.assertTrue(csq.supports_thinking_mode)


class TestConfigResolution(unittest.TestCase):
    def test_resolve_defaults(self):
        cfg = resolve_config(dry_run=True)
        self.assertEqual(cfg.provider, "mock")
        self.assertEqual(cfg.briq_sensitivity, 0)
        self.assertEqual(cfg.max_cycles, 0)
        self.assertEqual(cfg.max_time_seconds, 0)
        self.assertEqual(cfg.max_parallel_build_groups, 8)

    def test_cli_overrides(self):
        cfg = resolve_config(
            dry_run=True, briq_sensitivity=12, max_cycles=50,
            allow_dirty=True,
            runtime_mode="container", bridge_mode="process",
        )
        self.assertEqual(cfg.briq_sensitivity, 12)
        self.assertEqual(cfg.max_cycles, 50)
        self.assertTrue(cfg.allow_dirty)
        self.assertEqual(cfg.runtime_mode, "container")
        self.assertEqual(cfg.bridge_mode, "process")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            resolve_config(provider="nonexistent_provider_xyz")

    def test_stub_provider_raises(self):
        with self.assertRaises(ValueError):
            resolve_config(provider="jamini")

    def test_harness_checks(self):
        cfg = resolve_config(
            dry_run=True,
            harness_checks=["pytest -q", "ruff check ."],
        )
        checks = [c.command for c in cfg.harness_checks]
        self.assertIn("pytest -q", checks)
        self.assertIn("ruff check .", checks)

    def test_parallel_spawn_delay_default(self):
        cfg = resolve_config(dry_run=True)
        self.assertEqual(cfg.parallel_spawn_delay_seconds, 1.0)

    def test_parallel_spawn_delay_cli(self):
        cfg = resolve_config(
            dry_run=True,
            parallel_spawn_delay_seconds=2.5,
        )
        self.assertEqual(cfg.parallel_spawn_delay_seconds, 2.5)


class TestPerRoleReasoning(unittest.TestCase):
    def _resolve(self, text, **kwargs):
        path = _write_qq_yaml(text)
        try:
            return resolve_config(qq_path=path, dry_run=True, **kwargs)
        finally:
            os.unlink(path)

    def test_flat_model_form_is_backwards_compatible(self):
        cfg = self._resolve(
            "models:\n"
            "  qlarifier: deepseek-v4-flash\n"
            "  instruqtor: deepseek-v4-flash\n"
            "  construqtor: deepseek-v4-flash\n"
            "  inspeqtor: deepseek-v4-flash\n"
        )
        self.assertEqual(cfg.model_qlarifier, "deepseek-v4-flash")
        self.assertEqual(cfg.model_inspeqtor, "deepseek-v4-flash")
        self.assertEqual(cfg.reasoning_qlarifier, "")
        self.assertEqual(cfg.reasoning_construqtor, "")

    def test_structured_model_form_with_reasoning(self):
        cfg = self._resolve(
            "models:\n"
            "  qlarifier:\n"
            "    model: deepseek-v4-flash-thinking\n"
            "    reasoning: high\n"
            "  instruqtor:\n"
            "    model: deepseek-v4-flash-thinking\n"
            "    reasoning: high\n"
            "  construqtor:\n"
            "    model: deepseek-v4-flash\n"
            "    reasoning: low\n"
            "  inspeqtor:\n"
            "    model: deepseek-v4-flash-thinking\n"
            "    reasoning: max\n"
        )
        self.assertEqual(cfg.model_qlarifier, "deepseek-v4-flash-thinking")
        self.assertEqual(cfg.model_construqtor, "deepseek-v4-flash")
        self.assertEqual(cfg.reasoning_qlarifier, "high")
        self.assertEqual(cfg.reasoning_construqtor, "low")
        self.assertEqual(cfg.reasoning_inspeqtor, "max")

    def test_global_reasoning_cli_overrides_per_role(self):
        cfg = self._resolve(
            "models:\n"
            "  qlarifier:\n"
            "    model: deepseek-v4-flash-thinking\n"
            "    reasoning: high\n"
            "  construqtor:\n"
            "    model: deepseek-v4-flash\n"
            "    reasoning: low\n",
            reasoning_effort="max",
        )
        self.assertEqual(cfg.reasoning_effort, "max")
        self.assertEqual(cfg.reasoning_qlarifier, "max")
        self.assertEqual(cfg.reasoning_construqtor, "max")

    def test_invalid_reasoning_raises(self):
        with self.assertRaises(ValueError):
            self._resolve(
                "models:\n"
                "  qlarifier:\n"
                "    model: deepseek-v4-flash-thinking\n"
                "    reasoning: ultra\n"
            )


class TestBriqStatus(unittest.TestCase):
    def test_awaiting_review_exists(self):
        from qq.models import BriqStatus
        self.assertTrue(hasattr(BriqStatus, 'AWAITING_REVIEW'))
        self.assertEqual(BriqStatus.AWAITING_REVIEW.value, 'awaiting_review')


if __name__ == "__main__":
    unittest.main()
