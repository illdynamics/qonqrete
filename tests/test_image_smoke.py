"""Tests for image smoke-test — Venice-first, no CodeSeeq skill, no local tools."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


class TestBuildCodeSeeqEnv(unittest.TestCase):
    """Test build_codeseeq_env() environment propagation."""

    def test_includes_upstream_services_default(self):
        """build_codeseeq_env() includes CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES=true by default."""
        from qq.env import build_codeseeq_env
        with patch.dict(os.environ, {}, clear=True):
            env = build_codeseeq_env({})
            self.assertEqual(env.get("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES"), "true")

    def test_includes_runtime_mode_default(self):
        """build_codeseeq_env() includes CODESEEQ_RUNTIME_MODE=host by default."""
        from qq.env import build_codeseeq_env
        with patch.dict(os.environ, {}, clear=True):
            env = build_codeseeq_env({})
            self.assertEqual(env.get("CODESEEQ_RUNTIME_MODE"), "host")

    def test_does_not_overwrite_explicit_user_values(self):
        """build_codeseeq_env() preserves explicit user env values."""
        from qq.env import build_codeseeq_env
        base = {
            "CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES": "false",
            "CODESEEQ_RUNTIME_MODE": "container",
        }
        env = build_codeseeq_env(base)
        self.assertEqual(env["CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES"], "false")
        self.assertEqual(env["CODESEEQ_RUNTIME_MODE"], "container")

    def test_sets_defaults_when_keys_missing(self):
        """build_codeseeq_env() sets defaults when keys are missing from base env."""
        from qq.env import build_codeseeq_env
        env = build_codeseeq_env({"PATH": "/usr/bin"})
        self.assertEqual(env.get("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES"), "true")
        self.assertEqual(env.get("CODESEEQ_RUNTIME_MODE"), "host")

    def test_uses_os_environ_when_no_base_env(self):
        """build_codeseeq_env() uses os.environ when no base_env is passed."""
        from qq.env import build_codeseeq_env
        env = build_codeseeq_env()
        self.assertIn("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES", env)
        self.assertIn("CODESEEQ_RUNTIME_MODE", env)

    def test_preserves_other_env_vars(self):
        """build_codeseeq_env() preserves other environment variables."""
        from qq.env import build_codeseeq_env
        with patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/test"}, clear=True):
            env = build_codeseeq_env()
            self.assertEqual(env.get("PATH"), "/usr/bin")
            self.assertEqual(env.get("HOME"), "/home/test")


class TestCheckUpstreamServices(unittest.TestCase):
    """Test check_upstream_services_enabled()."""

    def test_returns_true_when_correctly_configured(self):
        """check_upstream_services_enabled() returns True when env is properly set."""
        from qq.env import check_upstream_services_enabled
        env = {
            "CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES": "true",
            "CODESEEQ_RUNTIME_MODE": "host",
        }
        ok, reason = check_upstream_services_enabled(env)
        self.assertTrue(ok, f"Expected True but got: {reason}")
        self.assertEqual(reason, "")

    def test_returns_false_when_upstream_disabled(self):
        """check_upstream_services_enabled() returns False when upstream services are disabled."""
        from qq.env import check_upstream_services_enabled
        env = {
            "CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES": "false",
            "CODESEEQ_RUNTIME_MODE": "host",
        }
        ok, reason = check_upstream_services_enabled(env)
        self.assertFalse(ok)
        self.assertIn("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES", reason)

    def test_returns_false_when_runtime_not_host(self):
        """check_upstream_services_enabled() returns False when runtime mode is not host."""
        from qq.env import check_upstream_services_enabled
        env = {
            "CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES": "true",
            "CODESEEQ_RUNTIME_MODE": "container",
        }
        ok, reason = check_upstream_services_enabled(env)
        self.assertFalse(ok)
        self.assertIn("CODESEEQ_RUNTIME_MODE", reason)

    def test_returns_false_when_both_missing(self):
        """check_upstream_services_enabled() returns False when both vars are missing."""
        from qq.env import check_upstream_services_enabled
        env = {}
        ok, reason = check_upstream_services_enabled(env)
        self.assertFalse(ok)
        self.assertIn("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES", reason)
        self.assertIn("CODESEEQ_RUNTIME_MODE", reason)


class TestVeniceEnvHelpers(unittest.TestCase):
    """Test Venice env helpers (duplicated from test_image_gen for smoke context)."""

    def test_get_venice_api_key_returns_key(self):
        """get_venice_api_key returns VENICE_API_KEY from env."""
        from qq.env import get_venice_api_key
        with patch.dict(os.environ, {"VENICE_API_KEY": "test-key-123"}, clear=True):
            self.assertEqual(get_venice_api_key(), "test-key-123")

    def test_get_venice_api_key_returns_none_when_missing(self):
        """get_venice_api_key returns None when VENICE_API_KEY is not set."""
        from qq.env import get_venice_api_key
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_venice_api_key())

    def test_venice_available_returns_true(self):
        """venice_available returns True when key is set."""
        from qq.env import venice_available
        with patch.dict(os.environ, {"VENICE_API_KEY": "test-key"}, clear=True):
            self.assertTrue(venice_available())

    def test_venice_available_returns_false(self):
        """venice_available returns False when key is missing."""
        from qq.env import venice_available
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(venice_available())

    def test_check_venice_configured_ok(self):
        """check_venice_configured returns True when key is set."""
        from qq.env import check_venice_configured
        with patch.dict(os.environ, {"VENICE_API_KEY": "key"}, clear=True):
            ok, reason = check_venice_configured()
            self.assertTrue(ok)
            self.assertEqual(reason, "")

    def test_check_venice_configured_fail(self):
        """check_venice_configured returns False when key is missing."""
        from qq.env import check_venice_configured
        with patch.dict(os.environ, {}, clear=True):
            ok, reason = check_venice_configured()
            self.assertFalse(ok)
            self.assertIn("VENICE_API_KEY", reason)


class TestImageSmokeMocked(unittest.TestCase):
    """Test the mocked image smoke-test path — Venice-first, mock fallback."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qq_img_smoke_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_image_smoke_creates_png_file(self):
        """Mocked image smoke test creates a valid PNG file in the repo root."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            result = run_image_smoke_test(output_dir=self.tmpdir, force_real=False)

        self.assertEqual(result, 0)
        image_path = os.path.join(self.tmpdir, "qonqrete_cybersquid.png")
        self.assertTrue(os.path.isfile(image_path), f"Image not found at {image_path}")
        with open(image_path, "rb") as f:
            header = f.read(8)
            self.assertTrue(header.startswith(b'\x89PNG\r\n\x1a\n'),
                            f"Not a valid PNG: {header[:20]}")

    def test_image_smoke_creates_meta_json(self):
        """Mocked image smoke test creates a metadata JSON file."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            result = run_image_smoke_test(output_dir=self.tmpdir, force_real=False)

        self.assertEqual(result, 0)
        meta_path = os.path.join(self.tmpdir, "qonqrete_cybersquid.meta.json")
        self.assertTrue(os.path.isfile(meta_path), f"Metadata not found at {meta_path}")

        with open(meta_path) as f:
            meta = json.load(f)

        self.assertIn("prompt", meta)
        self.assertIn("provider", meta)
        self.assertEqual(meta["provider"], "mock")
        self.assertIn("fallback", meta)
        self.assertEqual(meta["fallback"], "mock")
        self.assertIn("model_used", meta)
        self.assertEqual(meta["model_used"], "mock")
        self.assertIn("release_version", meta)
        self.assertIn("created_at", meta)
        self.assertIn("image_path", meta)

    def test_image_smoke_meta_has_required_fields(self):
        """Metadata JSON includes all required fields."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            run_image_smoke_test(output_dir=self.tmpdir, force_real=False)

        meta_path = os.path.join(self.tmpdir, "qonqrete_cybersquid.meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        required_fields = [
            "prompt", "provider", "fallback", "model_used",
            "duration_ms", "image_path", "created_at", "release_version",
        ]
        for field in required_fields:
            self.assertIn(field, meta, f"Missing required metadata field: {field}")

    def test_image_smoke_fails_with_force_real_and_no_key(self):
        """Image smoke test with --real fails when VENICE_API_KEY is not set."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            result = run_image_smoke_test(output_dir=self.tmpdir, force_real=True)

        self.assertEqual(result, 1)

    def test_image_smoke_succeeds_with_mock_no_key(self):
        """Image smoke test succeeds with mock fallback when no Venice key."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            result = run_image_smoke_test(output_dir=self.tmpdir, force_real=False)

        self.assertEqual(result, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "qonqrete_cybersquid.png")))

    def test_image_smoke_cli_command_exists(self):
        """python3 -m qq image-smoke-test --help should work."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "qq", "image-smoke-test", "--help"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("image-smoke-test", result.stdout)

    def test_image_smoke_cli_runs_mocked(self):
        """Running the CLI with no Venice key should exit 0 (mock fallback)."""
        import subprocess
        env = {**os.environ}
        # Ensure no VENICE_API_KEY leaks in
        env.pop("VENICE_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "qq", "image-smoke-test",
             "--output-dir", self.tmpdir],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT, env=env,
        )
        self.assertEqual(result.returncode, 0,
                         f"CLI failed: stdout={result.stdout} stderr={result.stderr}")
        self.assertIn("Image saved at:", result.stdout)

    def test_no_openai_api_key_required(self):
        """Image smoke test does not require or reference OPENAI_API_KEY."""
        from qq.image_smoke import run_image_smoke_test

        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("OPENAI_API_KEY", os.environ)
            result = run_image_smoke_test(output_dir=self.tmpdir, force_real=False)

        self.assertEqual(result, 0)
        # Verify metadata does not contain openai references
        meta_path = os.path.join(self.tmpdir, "qonqrete_cybersquid.meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertNotIn("used_openai_api_key", meta)
        self.assertNotIn("allow_upstream_codex_services", meta)
        self.assertNotIn("runtime_mode", meta)

    def test_cybersquid_prompt_contains_qq_emblem(self):
        """The image prompt must contain the ꝖꝖ emblem reference."""
        from qq.image_smoke import CYBERSQUID_PROMPT
        self.assertIn("ꝖꝖ", CYBERSQUID_PROMPT)
        self.assertIn("QonQrete", CYBERSQUID_PROMPT)
        self.assertIn("cybersquid", CYBERSQUID_PROMPT.lower())

    def test_default_output_dir_is_current_dir(self):
        """Default output_dir is '.' (repo root), not .qq/image-tests."""
        import inspect
        from qq.image_smoke import run_image_smoke_test
        sig = inspect.signature(run_image_smoke_test)
        self.assertEqual(sig.parameters["output_dir"].default, ".")
        # Verify the CLI also defaults to "."
        cli_path = os.path.join(PROJECT_ROOT, "qq", "cli.py")
        with open(cli_path) as f:
            content = f.read()
        self.assertIn('default="."', content.split("image-smoke-test")[1].split("image-smoke-test")[0]
                       if "image-smoke-test" in content else "")

    def test_no_codeseeq_references_in_smoke_module(self):
        """image_smoke.py does not reference CodeSeeq/imagegen skill in code."""
        smoke_path = os.path.join(PROJECT_ROOT, "qq", "image_smoke.py")
        with open(smoke_path) as f:
            raw = f.read()
        # Strip the module docstring entirely — it contains self-referential
        # mentions like "no codeseeq imagegen skill" that would trip us.
        # Find the end of the first triple-quote block
        end = raw.find('"""', 3)
        if end != -1:
            content = raw[end + 3:]
        else:
            content = raw
        # Now check only the actual code
        self.assertNotIn("codeseeq", content.lower())
        self.assertNotIn("pillow", content.lower())
        self.assertNotIn("PIL", content)
        self.assertNotIn("imagemagick", content.lower())
        self.assertNotIn("ImageMagick", content)
        self.assertNotIn("_generate_real_image_via_codeseeq", content)

    def test_no_dot_qq_output(self):
        """image_smoke.py does not write to .qq directory in code."""
        smoke_path = os.path.join(PROJECT_ROOT, "qq", "image_smoke.py")
        with open(smoke_path) as f:
            raw = f.read()
        import re
        # Strip docstring
        content = re.sub(r'^""".*?"""', '', raw, count=1, flags=re.DOTALL)
        self.assertNotIn(".qq", content)


class TestInspeQtorColorChanges(unittest.TestCase):
    """Test that inspeQtor display uses FULLY_DONE (green) and NOT_DONE (red)."""

    def test_qontroller_uses_full_done(self):
        """qontroller.py display messages use FULLY_DONE."""
        qontroller_path = os.path.join(PROJECT_ROOT, "qq", "qontroller.py")
        with open(qontroller_path) as f:
            content = f.read()
        self.assertIn("FULLY_DONE", content,
                      "qontroller.py must display FULLY_DONE")

    def test_qontroller_not_done_has_red_color(self):
        """qontroller.py NOT_DONE display uses red ANSI coloring."""
        qontroller_path = os.path.join(PROJECT_ROOT, "qq", "qontroller.py")
        with open(qontroller_path) as f:
            content = f.read()
        self.assertTrue("\x1b[31mNOT_DONE\x1b[0m" in content or "\\033[31mNOT_DONE" in content,
                      "NOT_DONE must be wrapped in red ANSI codes")

    def test_qontroller_full_done_has_green_color(self):
        """qontroller.py FULLY_DONE display uses green ANSI coloring."""
        qontroller_path = os.path.join(PROJECT_ROOT, "qq", "qontroller.py")
        with open(qontroller_path) as f:
            content = f.read()
        self.assertTrue("\x1b[32mFULLY_DONE\x1b[0m" in content or "\\033[32mFULLY_DONE" in content,
                      "FULLY_DONE must be wrapped in green ANSI codes")

    def test_cli_abort_mentions_full_done(self):
        """CLI abort message mentions FULLY_DONE."""
        cli_path = os.path.join(PROJECT_ROOT, "qq", "cli.py")
        with open(cli_path) as f:
            content = f.read()
        self.assertIn("FULLY_DONE", content,
                      "cli.py abort message must mention FULLY_DONE")
        self.assertNotIn("without FULLY_DONE", content,
                         "Old FULLY_DONE reference should be replaced")


class TestVersion200(unittest.TestCase):
    """Verify version 2.0.0 consistency."""

    def test_init_version_is_200(self):
        """qq.__version__ must be 2.0.0."""
        from qq import __version__
        self.assertEqual(__version__, "2.0.0")

    def test_pyproject_version_is_200(self):
        """pyproject.toml project version must be 2.0.0."""
        import tomllib
        toml_path = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(data["project"]["version"], "2.0.0")

    def test_package_fallback_version_is_200(self):
        """qq/package.py fallback version must be 2.0.0."""
        from qq.package import get_version
        self.assertEqual(get_version(), "2.0.0")

    def test_verify_archive_name_is_200(self):
        """qq/verify.py get_archive_name() must reference v2.0.0."""
        from qq.verify import get_archive_name
        name = get_archive_name()
        self.assertIn("qonqrete-qq-v2.0.0.zip", name)

    def test_meta_release_version_is_200(self):
        """Image metadata JSON includes release_version 2.0.0."""
        from qq.image_smoke import run_image_smoke_test
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                run_image_smoke_test(output_dir=tmpdir, force_real=False)

            meta_path = os.path.join(tmpdir, "qonqrete_cybersquid.meta.json")
            with open(meta_path) as f:
                meta = json.load(f)
            self.assertEqual(meta["release_version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
