from __future__ import annotations

from pathlib import Path
from typing import Any


class Compressor:
    name = "base"
    extensions: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._last_metadata: dict[str, Any] = {}

    def compress(self, file_path: Path, content: str) -> str:
        raise NotImplementedError

    def _set_last_metadata(self, **metadata: Any) -> None:
        self._last_metadata = dict(metadata)

    def consume_last_metadata(self) -> dict[str, Any]:
        payload = dict(self._last_metadata)
        self._last_metadata = {}
        return payload
