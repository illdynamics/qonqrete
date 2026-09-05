"""Tests for image generation module — Venice backend and config."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


class TestImageBackendConfig(unittest.TestCase):
    """Test ImageBackendConfig and VeniceImageConfig."""

    def test_default_provider_is_none(self):
        """Default image_backend provider is 'none'."""
        from qq.config import ImageBackendConfig
        cfg = ImageBackendConfig()
        self.assertEqual(cfg.provider, "none")
        self.assertFalse(cfg.enabled)
        self.assertFalse(cfg.is_venice)

    def test_venice_provider_enabled(self):
        """When provider is 'venice', backend is enabled."""
        from qq.config import ImageBackendConfig
        cfg = ImageBackendConfig(provider="venice")
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.is_venice)

    def test_venice_config_defaults(self):
        """VeniceImageConfig has sensible defaults."""
        from qq.config import VeniceImageConfig
        vc = VeniceImageConfig()
        self.assertEqual(vc.model, "auto")
        self.assertEqual(vc.aspect_ratio, "1:1")
        self.assertEqual(vc.resolution, "1K")
        self.assertEqual(vc.format, "png")
        self.assertEqual(vc.quality, "low")
        self.assertEqual(vc.cfg_scale, 7.5)
        self.assertEqual(vc.steps, 20)
        self.assertFalse(vc.safe_mode)

    def test_resolve_config_has_image_backend(self):
        """Resolved config includes image_backend field."""
        from qq.config import resolve_config
        cfg = resolve_config()
        self.assertIsNotNone(cfg.image_backend)
        # Provider may be "none" or "venice" depending on local config
        self.assertIn(cfg.image_backend.provider, ("none", "venice"))

    def test_resolve_config_with_venice(self):
        """Resolved config picks up venice provider from yaml."""
        from qq.config import resolve_config
        import tempfile, yaml

        config_data = {
            "provider": "codeseeq",
            "runtime_mode": "host",
            "image_backend": {
                "provider": "venice",
                "venice": {
                    "model": "z-image-turbo",
                    "aspect_ratio": "16:9",
                    "resolution": "2K",
                    "format": "jpeg",
                    "quality": "high",
                },
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            cfg = resolve_config(qq_path=config_path)
            self.assertEqual(cfg.image_backend.provider, "venice")
            self.assertTrue(cfg.image_backend.is_venice)
            self.assertEqual(cfg.image_backend.venice.model, "z-image-turbo")
            self.assertEqual(cfg.image_backend.venice.aspect_ratio, "16:9")
            self.assertEqual(cfg.image_backend.venice.resolution, "2K")
            self.assertEqual(cfg.image_backend.venice.format, "jpeg")
            self.assertEqual(cfg.image_backend.venice.quality, "high")
        finally:
            os.unlink(config_path)


class TestVeniceEnvHelpers(unittest.TestCase):
    """Test venice env helpers."""

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

    def test_get_venice_api_key_returns_none_when_empty(self):
        """get_venice_api_key returns None when VENICE_API_KEY is empty."""
        from qq.env import get_venice_api_key
        with patch.dict(os.environ, {"VENICE_API_KEY": ""}, clear=True):
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


class TestImageGenRequest(unittest.TestCase):
    """Test ImageGenRequest dataclass."""

    def test_defaults(self):
        """ImageGenRequest has sensible defaults."""
        from qq.image_gen import ImageGenRequest
        req = ImageGenRequest(prompt="test")
        self.assertEqual(req.prompt, "test")
        self.assertEqual(req.model, "auto")
        self.assertEqual(req.aspect_ratio, "1:1")
        self.assertEqual(req.resolution, "1K")
        self.assertEqual(req.format, "png")
        self.assertTrue(req.return_binary)

    def test_custom_params(self):
        """ImageGenRequest accepts custom parameters."""
        from qq.image_gen import ImageGenRequest
        req = ImageGenRequest(
            prompt="custom",
            model="z-image-turbo",
            aspect_ratio="16:9",
            resolution="4K",
            width=1280,
            height=720,
            quality="high",
            format="jpeg",
            cfg_scale=10.0,
            steps=30,
            seed=42,
            safe_mode=True,
            hide_watermark=True,
            negative_prompt="blurry",
            style="photorealistic",
        )
        self.assertEqual(req.model, "z-image-turbo")
        self.assertEqual(req.aspect_ratio, "16:9")
        self.assertEqual(req.resolution, "4K")
        self.assertEqual(req.width, 1280)
        self.assertEqual(req.height, 720)
        self.assertEqual(req.quality, "high")
        self.assertEqual(req.format, "jpeg")
        self.assertEqual(req.cfg_scale, 10.0)
        self.assertEqual(req.steps, 30)
        self.assertEqual(req.seed, 42)
        self.assertTrue(req.safe_mode)
        self.assertTrue(req.hide_watermark)
        self.assertEqual(req.negative_prompt, "blurry")
        self.assertEqual(req.style, "photorealistic")


class TestMockImageGen(unittest.TestCase):
    """Test mock image generation."""

    def test_generate_mock_png(self):
        """Mock generator creates a valid PNG."""
        from qq.image_gen import _generate_mock_image_bytes
        data = _generate_mock_image_bytes("png")
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'),
                        f"Not a valid PNG header: {data[:8]!r}")

    def test_generate_mock_jpeg(self):
        """Mock generator creates valid JPEG data."""
        from qq.image_gen import _generate_mock_image_bytes
        data = _generate_mock_image_bytes("jpeg")
        self.assertTrue(data.startswith(b'\xff\xd8\xff'),
                        f"Not a valid JPEG header: {data[:3]!r}")

    def test_generate_mock_png_non_empty(self):
        """Mock PNG is non-empty."""
        from qq.image_gen import _generate_mock_image_bytes
        data = _generate_mock_image_bytes("png")
        self.assertGreater(len(data), 50)


class TestGenerateImageFunction(unittest.TestCase):
    """Test the high-level generate_image function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qq_img_gen_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_image_mock_default(self):
        """generate_image with explicit none backend produces mock."""
        from qq.image_gen import generate_image
        from qq.config import ImageBackendConfig
        backend = ImageBackendConfig(provider="none")
        result = generate_image(prompt="test", backend=backend)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.image_data)
        self.assertEqual(result.model_used, "mock")
        self.assertEqual(result.metadata.get("backend"), "mock")

    def test_generate_image_saves_to_path(self):
        """generate_image saves to output_path when specified."""
        from qq.image_gen import generate_image
        from qq.config import ImageBackendConfig
        backend = ImageBackendConfig(provider="none")
        output_path = os.path.join(self.tmpdir, "test_out.png")
        result = generate_image(prompt="test", output_path=output_path, backend=backend)
        self.assertTrue(result.success)
        self.assertEqual(result.image_path, output_path)
        self.assertTrue(os.path.isfile(output_path))
        with open(output_path, "rb") as f:
            self.assertTrue(f.read(8).startswith(b'\x89PNG\r\n\x1a\n'))

    def test_generate_image_saves_jpeg(self):
        """generate_image can save JPEG format."""
        from qq.image_gen import generate_image
        from qq.config import ImageBackendConfig
        backend = ImageBackendConfig(provider="none")
        output_path = os.path.join(self.tmpdir, "test_out.jpg")
        result = generate_image(prompt="test", output_path=output_path, format="jpeg", backend=backend)
        self.assertTrue(result.success)
        self.assertTrue(os.path.isfile(output_path))

    def test_generate_image_result_has_base64(self):
        """ImageGenResult.base64 returns valid base64."""
        from qq.image_gen import generate_image
        from qq.config import ImageBackendConfig
        backend = ImageBackendConfig(provider="none")
        result = generate_image(prompt="test", backend=backend)
        self.assertTrue(result.success)
        b64 = result.base64
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 0)
        # Should decode back to same bytes
        import base64
        decoded = base64.b64decode(b64)
        self.assertEqual(decoded, result.image_data)


class TestVeniceProviderPayload(unittest.TestCase):
    """Test VeniceImageProvider payload building."""

    def test_build_payload_defaults(self):
        """VeniceImageProvider._build_payload produces correct defaults."""
        from qq.image_gen import VeniceImageProvider, ImageGenRequest
        provider = VeniceImageProvider(api_key="test-key")
        req = ImageGenRequest(prompt="test prompt")
        payload = provider._build_payload(req)
        self.assertEqual(payload["model"], "flux-dev")  # "auto" maps to flux-dev
        self.assertEqual(payload["prompt"], "test prompt")
        self.assertEqual(payload["format"], "png")
        self.assertEqual(payload["aspect_ratio"], "1:1")
        self.assertEqual(payload["resolution"], "1K")
        self.assertTrue(payload["return_binary"])
        self.assertFalse(payload["safe_mode"])

    def test_build_payload_custom_model(self):
        """Custom model is passed through."""
        from qq.image_gen import VeniceImageProvider, ImageGenRequest
        provider = VeniceImageProvider(api_key="test-key")
        req = ImageGenRequest(prompt="test", model="z-image-turbo")
        payload = provider._build_payload(req)
        self.assertEqual(payload["model"], "z-image-turbo")

    def test_build_payload_width_height(self):
        """Width/height override aspect_ratio."""
        from qq.image_gen import VeniceImageProvider, ImageGenRequest
        provider = VeniceImageProvider(api_key="test-key")
        req = ImageGenRequest(prompt="test", width=512, height=512)
        payload = provider._build_payload(req)
        self.assertEqual(payload["width"], 512)
        self.assertEqual(payload["height"], 512)
        # aspect_ratio should NOT be in payload when width/height are set
        self.assertNotIn("aspect_ratio", payload)

    def test_build_payload_quality(self):
        """Quality is included when specified."""
        from qq.image_gen import VeniceImageProvider, ImageGenRequest
        provider = VeniceImageProvider(api_key="test-key")
        req = ImageGenRequest(prompt="test", quality="high")
        payload = provider._build_payload(req)
        self.assertEqual(payload["quality"], "high")

    def test_build_payload_advanced_params(self):
        """Advanced params are included when non-default."""
        from qq.image_gen import VeniceImageProvider, ImageGenRequest
        provider = VeniceImageProvider(api_key="test-key")
        req = ImageGenRequest(
            prompt="test",
            cfg_scale=10.0,
            steps=30,
            seed=123,
            negative_prompt="bad stuff",
            style="3D Model",
        )
        payload = provider._build_payload(req)
        self.assertEqual(payload["cfg_scale"], 10.0)
        self.assertEqual(payload["steps"], 30)
        self.assertEqual(payload["seed"], 123)
        self.assertEqual(payload["negative_prompt"], "bad stuff")
        self.assertEqual(payload["style"], "3D Model")


class TestGenerateImageCLI(unittest.TestCase):
    """Test the generate-image CLI subcommand."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qq_img_cli_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_help(self):
        """qq generate-image --help works."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "qq", "generate-image", "--help"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("generate-image", result.stdout)

    def test_cli_generates_image(self):
        """qq generate-image produces an image file."""
        import subprocess
        output_path = os.path.join(self.tmpdir, "gen.png")
        env = {**os.environ, "VENICE_API_KEY": ""}
        result = subprocess.run(
            [sys.executable, "-m", "qq", "generate-image",
             "a test image", "--output", output_path, "--format", "png"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT, env=env,
        )
        self.assertEqual(result.returncode, 0,
                         f"CLI failed: stdout={result.stdout} stderr={result.stderr}")
        self.assertTrue(os.path.isfile(output_path))
        self.assertIn("Image generated successfully", result.stdout)

    def test_cli_json_output(self):
        """qq generate-image --json produces JSON output."""
        import subprocess
        env = {**os.environ, "VENICE_API_KEY": ""}
        result = subprocess.run(
            [sys.executable, "-m", "qq", "generate-image",
             "test", "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT, env=env,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertTrue(data["success"])
        self.assertEqual(data["model_used"], "mock")
        self.assertIn("image_path", data)

    def test_cli_writes_metadata(self):
        """qq generate-image --meta writes metadata JSON."""
        import subprocess
        env = {**os.environ, "VENICE_API_KEY": ""}
        meta_path = os.path.join(self.tmpdir, "meta.json")
        result = subprocess.run(
            [sys.executable, "-m", "qq", "generate-image",
             "test", "--meta", meta_path, "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT, env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.isfile(meta_path))
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["prompt"], "test")
        self.assertIn("model", meta)
        self.assertIn("created_at", meta)

    def test_cli_no_prompt_error(self):
        """qq generate-image without prompt returns error."""
        import subprocess
        # Need to make stdin not a TTY so it doesn't hang
        result = subprocess.run(
            [sys.executable, "-m", "qq", "generate-image"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT,
            input="",  # empty stdin
        )
        self.assertNotEqual(result.returncode, 0)


class TestImageGenResult(unittest.TestCase):
    """Test ImageGenResult data class."""

    def test_base64_empty_for_no_data(self):
        """base64 returns empty string when no image_data."""
        from qq.image_gen import ImageGenResult
        result = ImageGenResult(success=False, error="fail")
        self.assertEqual(result.base64, "")

    def test_base64_encodes_data(self):
        """base64 returns valid base64 encoding."""
        import base64
        from qq.image_gen import ImageGenResult
        data = b"fake image data"
        result = ImageGenResult(success=True, image_data=data)
        expected = base64.b64encode(data).decode("ascii")
        self.assertEqual(result.base64, expected)


if __name__ == "__main__":
    unittest.main()
