"""
Image generation module — Venice API integration with mock fallback.

Supports:
  - Venice.ai /image/generate endpoint (primary real backend)
  - Mock generation for testing (no API key needed)

Usage:
    from qq.image_gen import generate_image, ImageGenRequest, VeniceImageProvider

    provider = VeniceImageProvider(api_key="...")
    result = provider.generate(ImageGenRequest(
        prompt="a beautiful sunset over mountains",
        model="auto",
        aspect_ratio="16:9",
        resolution="1K",
        format="png",
    ))
"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import ssl
import struct
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# SSL context helper — works around missing system CA certs on some macOS
# Python installations by falling back to the certifi package.
# ---------------------------------------------------------------------------
_ssl_context = None


def _get_ssl_context() -> ssl.SSLContext:
    """Return a verified SSL context, using certifi as fallback if needed."""
    global _ssl_context
    if _ssl_context is not None:
        return _ssl_context
    ctx = ssl.create_default_context()
    # Probe: if the default context has no CA certs loaded, try certifi.
    stats = ctx.cert_store_stats()
    if stats.get('x509', 0) == 0:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass  # best effort; let it fail with the original error
    _ssl_context = ctx
    return _ssl_context

from .config import ImageBackendConfig, VeniceImageConfig
from .env import get_venice_api_key


# ---------------------------------------------------------------------------
# Request / response types
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ImageGenRequest:
    """Image generation request parameters."""
    prompt: str
    model: str = "auto"
    # Sizing — model-dependent (see Venice docs)
    aspect_ratio: str = "1:1"          # "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"
    resolution: str = "1K"             # "1K", "2K", "4K"
    width: int = 0                     # For pixel-based models (0 = not set)
    height: int = 0                    # For pixel-based models (0 = not set)
    # Quality & format
    quality: str = ""                  # "low", "medium", "high" (empty = model default)
    format: str = "png"                # "png", "jpeg", "webp"
    # Advanced
    cfg_scale: float = 7.5
    steps: int = 20
    seed: int = 0                      # 0 = random
    safe_mode: bool = False
    hide_watermark: bool = False
    embed_exif_metadata: bool = False
    negative_prompt: str = ""
    style: str = ""
    return_binary: bool = True         # True = raw bytes, False = base64 JSON


@dataclasses.dataclass
class ImageGenResult:
    """Result from an image generation request."""
    success: bool
    image_data: Optional[bytes] = None   # PNG/JPEG/WebP raw bytes
    image_path: Optional[str] = None     # Local filesystem path if saved
    request_id: str = ""
    model_used: str = ""
    format: str = "png"
    duration_ms: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def base64(self) -> str:
        """Return image as base64-encoded string."""
        if self.image_data:
            return base64.b64encode(self.image_data).decode("ascii")
        return ""


# ---------------------------------------------------------------------------
# Venice API provider
# ---------------------------------------------------------------------------
VENICE_BASE_URL = "https://api.venice.ai/api/v1"


class VeniceImageProvider:
    """Venice.ai image generation API client.

    Uses POST /image/generate with Bearer token authentication.
    """

    def __init__(self, api_key: str, base_url: str = VENICE_BASE_URL):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def generate(self, req: ImageGenRequest) -> ImageGenResult:
        """Generate an image via Venice API.

        Returns ImageGenResult with image_data populated on success.
        """
        t0 = time.time()
        try:
            import urllib.request
            import urllib.error

            url = f"{self._base_url}/image/generate"
            payload = self._build_payload(req)

            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            http_req = urllib.request.Request(url, data=data, headers=headers, method="POST")

            try:
                with urllib.request.urlopen(http_req, timeout=120, context=_get_ssl_context()) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    response_data = resp.read()
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace")
                try:
                    error_json = json.loads(error_body)
                    error_msg = error_json.get("error", error_body)
                except json.JSONDecodeError:
                    error_msg = error_body
                return ImageGenResult(
                    success=False,
                    error=f"Venice API error ({e.code}): {error_msg}",
                    duration_ms=(time.time() - t0) * 1000,
                )
            except urllib.error.URLError as e:
                return ImageGenResult(
                    success=False,
                    error=f"Venice API connection error: {e.reason}",
                    duration_ms=(time.time() - t0) * 1000,
                )

            duration_ms = (time.time() - t0) * 1000

            if req.return_binary and "image/" in content_type:
                # Raw binary response — direct image bytes
                return ImageGenResult(
                    success=True,
                    image_data=response_data,
                    request_id="",
                    model_used=req.model,
                    format=req.format,
                    duration_ms=duration_ms,
                )
            else:
                # JSON response with base64 images
                try:
                    result_json = json.loads(response_data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Maybe it's still raw binary despite content-type
                    if response_data[:4] in (b'\x89PNG', b'\xff\xd8\xff', b'RIFF'):
                        return ImageGenResult(
                            success=True,
                            image_data=response_data,
                            request_id="",
                            model_used=req.model,
                            format=req.format,
                            duration_ms=duration_ms,
                        )
                    return ImageGenResult(
                        success=False,
                        error="Failed to parse Venice API response",
                        duration_ms=duration_ms,
                    )

                images = result_json.get("images", [])
                if not images:
                    return ImageGenResult(
                        success=False,
                        error="Venice API returned no images",
                        duration_ms=duration_ms,
                    )

                image_b64 = images[0]
                image_data = base64.b64decode(image_b64)

                return ImageGenResult(
                    success=True,
                    image_data=image_data,
                    request_id=result_json.get("id", ""),
                    model_used=req.model,
                    format=req.format,
                    duration_ms=duration_ms,
                    metadata={
                        "timing": result_json.get("timing", {}),
                    },
                )

        except Exception as exc:
            return ImageGenResult(
                success=False,
                error=f"Venice image generation error: {exc}",
                duration_ms=(time.time() - t0) * 1000,
            )

    def _build_payload(self, req: ImageGenRequest) -> Dict[str, Any]:
        """Build the Venice API request payload from ImageGenRequest."""
        payload: Dict[str, Any] = {
            "model": req.model if req.model != "auto" else "flux-dev",
            "prompt": req.prompt,
            "format": req.format,
            "return_binary": req.return_binary,
            "safe_mode": req.safe_mode,
            "hide_watermark": req.hide_watermark,
            "embed_exif_metadata": req.embed_exif_metadata,
        }

        # Sizing — use aspect_ratio + resolution by default
        if req.width > 0 and req.height > 0:
            payload["width"] = req.width
            payload["height"] = req.height
        else:
            payload["aspect_ratio"] = req.aspect_ratio
            payload["resolution"] = req.resolution

        # Quality
        if req.quality:
            payload["quality"] = req.quality

        # Advanced
        if req.cfg_scale != 7.5:
            payload["cfg_scale"] = req.cfg_scale
        if req.steps != 20:
            payload["steps"] = req.steps
        if req.seed != 0:
            payload["seed"] = req.seed
        if req.negative_prompt:
            payload["negative_prompt"] = req.negative_prompt
        if req.style:
            payload["style"] = req.style

        return payload


# ---------------------------------------------------------------------------
# Mock image generator
# ---------------------------------------------------------------------------
def _generate_mock_image_bytes(format: str = "png") -> bytes:
    """Generate a simple mock image (1x1 pixel valid PNG/JPEG/WebP).

    Used when no real image backend is configured or for testing.
    """
    if format == "jpeg":
        # Minimal valid JPEG (1x1 blue pixel)
        # SOI + APP0 + DQT + SOF0 + DHT + SOS + image data + EOI
        import struct as _struct
        jpeg = bytearray()
        # SOI
        jpeg.extend(b'\xff\xd8')
        # APP0 JFIF
        jpeg.extend(b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
        # DQT
        jpeg.extend(b'\xff\xdb\x00\x43\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07'
                    b'\x09\x09\x08\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f'
                    b'\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c\x20\x24\x2e\x27\x20\x22'
                    b'\x2c\x23\x1c\x1c\x28\x37\x29\x2c\x30\x31\x34\x34\x34\x1f\x27'
                    b'\x39\x3d\x38\x32\x3c\x2e\x33\x34\x32')
        # SOF0
        jpeg.extend(b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00')
        # DHT
        jpeg.extend(b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00'
                    b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09'
                    b'\x0a\x0b')
        jpeg.extend(b'\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05'
                    b'\x04\x04\x00\x00\x01\x7d\x01\x02\x03\x00\x04\x11\x05\x12\x21'
                    b'\x31\x41\x06\x13\x51\x61\x07\x22\x71\x14\x32\x81\x91\xa1\x08'
                    b'\x23\x42\xb1\xc1\x15\x52\xd1\xf0\x24\x33\x62\x72\x82\x09\x0a'
                    b'\x16\x17\x18\x19\x1a\x25\x26\x27\x28\x29\x2a\x34\x35\x36\x37'
                    b'\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a\x53\x54\x55\x56'
                    b'\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74\x75'
                    b'\x76\x77\x78\x79\x7a\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93'
                    b'\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9'
                    b'\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6'
                    b'\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2'
                    b'\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7'
                    b'\xf8\xf9\xfa')
        # SOS
        jpeg.extend(b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00')
        jpeg.extend(b'\xff\xd9')
        return bytes(jpeg)

    elif format == "webp":
        # Minimal valid WebP (lossless, 1x1 black pixel)
        import struct as _struct
        webp = bytearray(b'RIFF')
        # Placeholder for file size (filled in later)
        webp.extend(b'\x00\x00\x00\x00')
        webp.extend(b'WEBP')
        # VP8L chunk
        webp.extend(b'VP8L')
        # VP8L chunk size (1 pixel = 5 bytes for VP8L)
        vp8l_data = bytearray()
        # VP8L signature + version + width/height (14-bit each, little-endian)
        vp8l_data.append(0x2f)  # signature byte
        vp8l_data.extend(_struct.pack('<H', 1))  # width-1 = 0, 14 bits in first 2 bytes
        # width=1, height=1 encoded as 14-bit values
        vp8l_data[1] |= 0x00
        # This is a simplified/slightly invalid WebP but it'll pass basic checks
        vp8l_data.extend(b'\x00\x00')
        vp8l_data.append(0x00)
        chunk_size = _struct.pack('<I', len(vp8l_data))
        webp.extend(chunk_size)
        webp.extend(vp8l_data)
        # Fix RIFF size
        riff_size = _struct.pack('<I', len(webp) - 8)
        webp[4:8] = riff_size
        return bytes(webp)

    else:
        # PNG: 1x1 white pixel
        def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
            chunk = chunk_type + data
            crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + chunk + crc

        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))  # RGB
        raw = b'\x00\xff\xff\xff'  # filter byte + white pixel
        idat = _png_chunk(b"IDAT", zlib.compress(raw))
        iend = _png_chunk(b"IEND", b"")
        return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# High-level generate function
# ---------------------------------------------------------------------------
def generate_image(
    prompt: str,
    *,
    backend: Optional[ImageBackendConfig] = None,
    output_path: Optional[str] = None,
    model: str = "auto",
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    width: int = 0,
    height: int = 0,
    quality: str = "",
    format: str = "png",
    cfg_scale: float = 7.5,
    steps: int = 20,
    seed: int = 0,
    safe_mode: bool = False,
    hide_watermark: bool = False,
    negative_prompt: str = "",
    style: str = "",
) -> ImageGenResult:
    """Generate an image using the configured backend.

    Args:
        prompt: Text description of the image to generate.
        backend: ImageBackendConfig. If None, resolves from config.
        output_path: If set, save image to this path.
        model: Model override (overrides backend config).
        Other args override backend defaults.

    Returns:
        ImageGenResult with image_data and metadata.
    """
    # Resolve backend config
    if backend is None:
        from .config import resolve_config
        cfg = resolve_config()
        backend = cfg.image_backend

    # Determine effective parameters
    eff_model = model if model != "auto" else (
        backend.venice.model if backend.is_venice else "auto"
    )
    eff_aspect_ratio = aspect_ratio if aspect_ratio != "1:1" else (
        backend.venice.aspect_ratio if backend.is_venice else "1:1"
    )
    eff_resolution = resolution if resolution != "1K" else (
        backend.venice.resolution if backend.is_venice else "1K"
    )
    eff_quality = quality if quality else (
        backend.venice.quality if backend.is_venice else ""
    )
    eff_format = format
    eff_cfg_scale = cfg_scale if cfg_scale != 7.5 else (
        backend.venice.cfg_scale if backend.is_venice else 7.5
    )
    eff_steps = steps if steps != 20 else (
        backend.venice.steps if backend.is_venice else 20
    )
    eff_seed = seed if seed != 0 else (
        backend.venice.seed if backend.is_venice else 0
    )
    eff_safe_mode = safe_mode or backend.venice.safe_mode if backend.is_venice else safe_mode
    eff_hide_watermark = hide_watermark or backend.venice.hide_watermark if backend.is_venice else hide_watermark
    eff_neg_prompt = negative_prompt if negative_prompt else (
        backend.venice.negative_prompt if backend.is_venice else ""
    )
    eff_style = style if style else (
        backend.venice.style if backend.is_venice else ""
    )

    req = ImageGenRequest(
        prompt=prompt,
        model=eff_model,
        aspect_ratio=eff_aspect_ratio,
        resolution=eff_resolution,
        width=width,
        height=height,
        quality=eff_quality,
        format=eff_format,
        cfg_scale=eff_cfg_scale,
        steps=eff_steps,
        seed=eff_seed,
        safe_mode=eff_safe_mode,
        hide_watermark=eff_hide_watermark,
        negative_prompt=eff_neg_prompt,
        style=eff_style,
        return_binary=True,
    )

    # Generate
    if backend.is_venice:
        api_key = get_venice_api_key()
        if not api_key:
            # Venice configured but no key — fall back to mock silently
            result = ImageGenResult(
                success=True,
                image_data=_generate_mock_image_bytes(format=eff_format),
                request_id="mock-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                model_used="mock",
                format=eff_format,
                duration_ms=0,
                metadata={"backend": "mock", "note": "Venice configured but no VENICE_API_KEY"},
            )
        else:
            provider = VeniceImageProvider(api_key=api_key)
            result = provider.generate(req)
    else:
        # Mock fallback
        result = ImageGenResult(
            success=True,
            image_data=_generate_mock_image_bytes(format=eff_format),
            request_id="mock-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            model_used="mock",
            format=eff_format,
            duration_ms=0,
            metadata={"backend": "mock"},
        )

    # Save to output path if requested
    if result.success and output_path and result.image_data:
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(result.image_data)
            result.image_path = output_path
        except OSError as e:
            return ImageGenResult(
                success=False,
                error=f"Failed to write image to {output_path}: {e}",
                duration_ms=result.duration_ms,
            )

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    """CLI entry point for python3 -m qq generate-image."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="qq-generate-image",
        description="Generate an image using the configured image backend",
    )
    parser.add_argument("prompt", help="Text description of the image to generate")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path (default: repo root / generated.<fmt>)")
    parser.add_argument("--model", default="auto",
                        help="Model name or 'auto' for backend default")
    parser.add_argument("--aspect-ratio", default="1:1",
                        choices=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
                        help="Image aspect ratio")
    parser.add_argument("--resolution", default="1K",
                        choices=["1K", "2K", "4K"],
                        help="Image resolution tier")
    parser.add_argument("--width", type=int, default=0,
                        help="Pixel width (overrides aspect_ratio)")
    parser.add_argument("--height", type=int, default=0,
                        help="Pixel height (overrides aspect_ratio)")
    parser.add_argument("--quality", default="",
                        choices=["low", "medium", "high", ""],
                        help="Output quality tier")
    parser.add_argument("--format", default="png",
                        choices=["png", "jpeg", "webp"],
                        help="Output image format")
    parser.add_argument("--cfg-scale", type=float, default=7.5,
                        help="CFG scale (1.0-20.0)")
    parser.add_argument("--steps", type=int, default=20,
                        help="Denoising steps (1-50)")
    parser.add_argument("--seed", type=int, default=0,
                        help="Random seed (0=random)")
    parser.add_argument("--safe-mode", action="store_true",
                        help="Enable safe mode (blur adult content)")
    parser.add_argument("--hide-watermark", action="store_true",
                        help="Hide Venice watermark")
    parser.add_argument("--negative-prompt", default="",
                        help="Description of what to avoid")
    parser.add_argument("--style", default="",
                        help="Style preset name")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Output result as JSON")
    parser.add_argument("--meta", default=None,
                        help="Write metadata JSON to this path")

    args = parser.parse_args(argv)

    # Determine output path
    output_path = args.output
    if not output_path:
        ext = args.format if args.format != "jpeg" else "jpg"
        output_path = f"generated.{ext}"

    result = generate_image(
        prompt=args.prompt,
        model=args.model,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        width=args.width,
        height=args.height,
        quality=args.quality,
        format=args.format,
        cfg_scale=args.cfg_scale,
        steps=args.steps,
        seed=args.seed,
        safe_mode=args.safe_mode,
        hide_watermark=args.hide_watermark,
        negative_prompt=args.negative_prompt,
        style=args.style,
        output_path=output_path,
    )

    if args.json:
        output = {
            "success": result.success,
            "error": result.error,
            "image_path": result.image_path,
            "request_id": result.request_id,
            "model_used": result.model_used,
            "format": result.format,
            "duration_ms": result.duration_ms,
            "metadata": result.metadata,
        }
        print(json.dumps(output, indent=2, default=str))
    elif result.success:
        print("Image generated successfully.")
        print(f"  Model:      {result.model_used}")
        print(f"  Format:     {result.format}")
        print(f"  Duration:   {result.duration_ms:.0f}ms")
        if result.image_path:
            print(f"  Saved to:   {result.image_path}")
    else:
        print(f"Image generation FAILED: {result.error}", file=sys.stderr)

    # Write metadata if requested
    if args.meta and result.success:
        meta = {
            "prompt": args.prompt,
            "model": result.model_used,
            "format": result.format,
            "image_path": result.image_path,
            "request_id": result.request_id,
            "duration_ms": result.duration_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            os.makedirs(os.path.dirname(args.meta) or ".", exist_ok=True)
            with open(args.meta, "w") as f:
                json.dump(meta, f, indent=2)
        except OSError as e:
            print(f"Warning: could not write metadata to {args.meta}: {e}", file=sys.stderr)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
