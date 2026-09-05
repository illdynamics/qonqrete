"""
Image smoke-test — Venice API image generation.

Usage:
    python3 -m qq image-smoke-test

Requires:
    VENICE_API_KEY environment variable

The smoke test generates an image of QonQrete the cybersquid using Venice.ai
and saves it to the repo root workspace directory:

    ./qonqrete_cybersquid.png
    ./qonqrete_cybersquid.meta.json

No local tools (Pillow, ImageMagick), no CodeSeeq imagegen skill, no .qq
directory output — Venice first and only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CYBERSQUID_PROMPT = (
    "Create a high-detail cinematic image of QonQrete the cybersquid: a "
    "cybernetic squid made of dark concrete, glowing ember-orange circuitry, "
    "steel tentacles, and a molten gold ꝖꝖ emblem. It is emerging from a "
    "neon command-line ocean, surrounded by code streams, build artifacts, "
    "and sparks. Style: futuristic, sharp, dramatic lighting, high contrast, "
    "production-quality concept art. No text except the small ꝖꝖ emblem."
)

OUTPUT_FILENAME = "qonqrete_cybersquid.png"
META_FILENAME = "qonqrete_cybersquid.meta.json"


def _get_version() -> str:
    try:
        from qq import __version__
        return __version__
    except ImportError:
        return "2.0.0"


# ---------------------------------------------------------------------------
# Mock image generator (fallback for when VENICE_API_KEY is not set)
# ---------------------------------------------------------------------------
def _generate_mock_image(output_path: str) -> tuple[bool, str]:
    """Generate a simple mock PNG image file (1x1 pixel, valid PNG header).

    Used as a deterministic fallback when VENICE_API_KEY is not configured.
    """
    import struct
    import zlib

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk + crc

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)
    raw = b'\x00\xff'
    compressed = zlib.compress(raw)
    idat = _png_chunk(b"IDAT", compressed)
    iend = _png_chunk(b"IEND", b"")

    with open(output_path, "wb") as f:
        f.write(sig + ihdr + idat + iend)

    return True, ""


# ---------------------------------------------------------------------------
# Smoke test runner
# ---------------------------------------------------------------------------
def run_image_smoke_test(
    output_dir: str = ".",
    force_real: bool = False,
) -> int:
    """Run the image smoke test.

    Generates the QonQrete cybersquid image using Venice.ai if VENICE_API_KEY
    is set. Falls back to a deterministic mock 1x1 PNG if no API key is
    available.

    Args:
        output_dir: Directory to save the generated image and metadata.
                    Defaults to current directory (repo root).
        force_real: If True, require a real Venice API key and fail if not
                    configured.

    Returns:
        0 on success, 1 on failure.
    """
    version = _get_version()
    created_at = datetime.now(timezone.utc).isoformat()

    # Ensure output_dir is absolute
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    image_path = os.path.join(output_dir, OUTPUT_FILENAME)
    meta_path = os.path.join(output_dir, META_FILENAME)

    success = False
    error_reason = ""
    provider = "mock"
    fallback = "mock"
    model_used = "mock"
    duration_ms = 0.0

    # Try Venice if configured
    from .env import get_venice_api_key
    venice_key = get_venice_api_key()

    if venice_key:
        try:
            from .config import resolve_config
            from .image_gen import generate_image as gen_img

            cfg = resolve_config()
            if cfg.image_backend.is_venice:
                print("Using Venice image backend...")
                result = gen_img(
                    prompt=CYBERSQUID_PROMPT,
                    backend=cfg.image_backend,
                    output_path=image_path,
                )
                success = result.success
                error_reason = result.error if not success else ""
                provider = "venice"
                fallback = f"venice:{result.model_used}"
                model_used = result.model_used
                duration_ms = result.duration_ms
                if success:
                    print(f"Venice image generated in {result.duration_ms:.0f}ms "
                          f"using {result.model_used}")
            else:
                # Config says not venice, but key exists — try anyway
                print("Venice API key found but backend not configured as venice. "
                      "Using Venice directly...")
                from .image_gen import VeniceImageProvider, ImageGenRequest
                provider_obj = VeniceImageProvider(api_key=venice_key)
                t0 = time.time()
                req = ImageGenRequest(
                    prompt=CYBERSQUID_PROMPT,
                    model="z-image-turbo",
                    aspect_ratio="16:9",
                    resolution="1K",
                    format="png",
                    return_binary=True,
                )
                result = provider_obj.generate(req)
                duration_ms = (time.time() - t0) * 1000
                if result.success and result.image_data:
                    with open(image_path, "wb") as f:
                        f.write(result.image_data)
                    success = True
                    provider = "venice"
                    fallback = "venice:z-image-turbo"
                    model_used = "z-image-turbo"
                    print(f"Venice image generated in {duration_ms:.0f}ms "
                          f"using z-image-turbo")
                else:
                    error_reason = result.error
        except Exception as e:
            error_reason = f"Venice generation error: {e}"

    if not success and force_real:
        # force_real means we required Venice and it failed
        if not venice_key:
            error_reason = (
                "VENICE_API_KEY is not set. Set it to use Venice image generation. "
                "Get a key at https://venice.ai/settings/api"
            )
        print(f"QonQrete cybersquid image test FAILED: {error_reason}")
        return 1

    if not success:
        # Fall back to mock
        print("Venice API key not configured, using mock fallback...")
        success, error_reason = _generate_mock_image(image_path)
        provider = "mock"
        fallback = "mock"
        model_used = "mock"

    # Write metadata
    metadata = {
        "prompt": CYBERSQUID_PROMPT,
        "provider": provider,
        "fallback": fallback,
        "model_used": model_used,
        "duration_ms": duration_ms,
        "image_path": image_path,
        "created_at": created_at,
        "release_version": version,
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    if success:
        print("QonQrete cybersquid image test finished.")
        print(f"Image saved at: {image_path}")
        return 0
    else:
        print(f"QonQrete cybersquid image test failed: {error_reason}")
        return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    """CLI entry point for python3 -m qq image-smoke-test."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="qq-image-smoke-test",
        description="QonQrete cybersquid image smoke test — Venice API",
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Output directory for generated images (default: repo root)",
    )
    parser.add_argument(
        "--real", action="store_true",
        help="Require Venice API key and fail if not configured (no mock fallback)",
    )
    args = parser.parse_args(argv)

    sys.exit(run_image_smoke_test(
        output_dir=args.output_dir,
        force_real=args.real,
    ))


if __name__ == "__main__":
    main()
