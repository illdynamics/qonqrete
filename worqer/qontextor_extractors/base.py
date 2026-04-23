from __future__ import annotations

from pathlib import Path

from .graph import FileContext


class Extractor:
    name = "base"
    extensions: tuple[str, ...] = ()

    def extract(
        self,
        project_path: Path,
        file_path: Path,
        content: str,
        local_mode: str = "complex",
    ) -> FileContext:
        raise NotImplementedError
