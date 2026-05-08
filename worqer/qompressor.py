#!/usr/bin/env python3
# worqer/qompressor.py
"""
QonQrete Qompressor - Deterministic Multi-language Structural Skeletonizer

Default identity:
- structural
- readable
- deterministic
- offline-safe by default
- adapter-based

First-class languages:
- Python
- shell
- JavaScript / TypeScript
- HTML / CSS

Tree-sitter is an optional fallback path for unsupported parseable languages when
its runtime + grammars are available. It is not the primary path for the
first-class languages.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def _repo_version() -> str:
    try:
        return (Path(__file__).resolve().parents[1] / 'VERSION').read_text(encoding='utf-8').strip()
    except Exception:
        return 'unknown'


from qompressor_extractors.common import (
    CODE_EXTENSIONS,
    comment_marker_for_suffix,
    normalize_blank_lines,
    should_compress,
    should_copy,
)
from qompressor_extractors.registry import get_compressor_for_file
from qompressor_extractors.tree_sitter_fallback import TreeSitterFallback, fallback_compress
from runtime_capabilities import capability_report_json, collect_runtime_capabilities, format_capability_report

try:
    from path_hygiene import INFRA_DIR_NAMES, is_generated_output_dir, is_source_junk_file
except ImportError:
    INFRA_DIR_NAMES = frozenset({
        ".git",
        ".venv",
        ".test_venv",
        "node_modules",
        ".gradle",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".validation-env-cache",
        "__MACOSX",
    })

    def is_generated_output_dir(path: Path) -> bool:
        return path.name == "out" and path.parent.name == "vscode-extension"

    def is_source_junk_file(path: Path) -> bool:
        return path.name == ".DS_Store" or path.name.startswith("._") or path.suffix == ".pyc"


def compress_generic(content: str, file_path: str | Path | None = None) -> str:
    """Last-resort structural stripper for unsupported languages or parse failures."""
    suffix = Path(file_path).suffix.lower() if file_path else ''
    marker = comment_marker_for_suffix(suffix)
    lines = content.splitlines()
    output: list[str] = []
    block_depth = 0
    kept_header = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(('#', '//', '/*', '*')):
            output.append(line)
            continue
        if re.match(r'^(?:import|from|using|use|package|namespace|include|require|module)', stripped):
            output.append(line)
            continue
        if re.match(r'^(?:class|interface|trait|enum|struct|fn|func|def|sub|public class|private class|module)', stripped):
            output.append(line)
            kept_header = True
            if stripped.endswith('{'):
                block_depth += 1
            continue
        if re.match(r'^(?:export\s+)?(?:const|let|var|val)\s+[A-Za-z_][\w$]*\s*=\s*[^\{]{0,100}$', stripped):
            output.append(line)
            continue
        if '{' in stripped and not kept_header:
            output.append(line)
            output.append((' ' * (len(line) - len(line.lstrip()) + 2)) + marker)
            kept_header = True
            block_depth += stripped.count('{') - stripped.count('}')
            continue
        if '}' in stripped:
            output.append(line)
            block_depth = max(0, block_depth - stripped.count('}'))
            kept_header = False
            continue
    return normalize_blank_lines('\n'.join(output)) or content



def compress_file_content_with_metadata(file_path: str, content: str) -> tuple[str, dict[str, Any]]:
    path = Path(file_path)
    compressor = get_compressor_for_file(path)
    if compressor is not None:
        try:
            result = compressor.compress(path, content)
            metadata = compressor.consume_last_metadata() if hasattr(compressor, 'consume_last_metadata') else {}
            if result and result.strip():
                metadata = dict(metadata)
                metadata.setdefault('mode', metadata.get('mode') or compressor.name)
                metadata.setdefault('strategy', metadata.get('strategy') or 'native')
                metadata.setdefault('fidelity', 'skeleton')
                metadata.setdefault('compressor_status', 'ok')
                return result, metadata
        except Exception as exc:
            return content, {
                'mode': 'full_due_parse_error',
                'strategy': 'copy',
                'tooling': getattr(compressor, 'name', 'unknown'),
                'note': str(exc),
                'fidelity': 'full_due_parse_error',
                'compressor_status': 'parse_failed_passthrough',
            }
        else:
            metadata = {
                'mode': 'compressor_empty',
                'strategy': 'fallback',
                'tooling': getattr(compressor, 'name', 'unknown'),
                'note': 'compressor returned empty output',
                'fidelity': 'skeleton',
                'compressor_status': 'ok',
            }
    else:
        metadata = {
            'mode': 'no_registered_compressor',
            'strategy': 'fallback',
            'tooling': 'none',
            'fidelity': 'skeleton',
            'compressor_status': 'ok',
        }

    ts_availability = TreeSitterFallback().availability(path)
    ts_result = fallback_compress(path, content)
    if ts_result and ts_result.strip():
        metadata = {
            'mode': 'tree_sitter_fallback',
            'strategy': 'fallback',
            'tooling': 'Tree-sitter fallback',
            'fidelity': 'skeleton',
            'compressor_status': 'ok',
        }
        return ts_result, metadata

    if path.suffix.lower() in CODE_EXTENSIONS:
        note = ts_availability.reason if not ts_availability.available else None
        metadata = {
            'mode': 'generic_fallback',
            'strategy': 'fallback',
            'tooling': 'generic structural stripper',
            'fidelity': 'skeleton',
            'compressor_status': 'ok',
        }
        if note:
            metadata['note'] = note
        return compress_generic(content, path), metadata
    return content, {
        'mode': 'copied_passthrough',
        'strategy': 'copy',
        'tooling': 'raw copy',
        'fidelity': 'full',
        'compressor_status': 'copy_passthrough',
    }



def compress_file_content(file_path: str, content: str) -> str:
    return compress_file_content_with_metadata(file_path, content)[0]


def _source_sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()


def _skeleton_header_lines(path: Path, rel: str) -> list[str]:
    suffix = path.suffix.lower()
    rel = str(rel).replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith("qodeyard/"):
        rel = rel[len("qodeyard/"):]
    if suffix in {'.html', '.htm', '.xml'}:
        return [
            "<!-- QONQ_FIDELITY: skeleton -->",
            f"<!-- QONQ_SOURCE: qodeyard/{rel} -->",
            "<!-- QONQ_DO_NOT_WRITE_BACK: true -->",
        ]
    marker = "#" if suffix in {'.py', '.sh', '.bash', '.zsh', '.ksh', '.rb', '.pl'} else "//"
    return [
        f"{marker} QONQ_FIDELITY: skeleton",
        f"{marker} QONQ_SOURCE: qodeyard/{rel}",
        f"{marker} QONQ_DO_NOT_WRITE_BACK: true",
    ]


def _prepend_skeleton_header(path: Path, rel: str, text: str) -> str:
    lowered = text.lower()
    if "qonq_fidelity: skeleton" in lowered and "qonq_do_not_write_back: true" in lowered:
        return text
    header = "\n".join(_skeleton_header_lines(path, rel))
    return f"{header}\n\n{text}"



def process_file(
    source_path: Path,
    dest_path: Path,
    *,
    source_root: Path | None = None,
    rel_path: str | None = None,
) -> dict[str, Any]:
    """Reads source, compresses if needed, writes to dest."""
    print(f"     - Processing: {source_path.name}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if rel_path is not None:
        rel = str(rel_path).replace("\\", "/")
    elif source_root is not None:
        try:
            rel = source_path.relative_to(source_root).as_posix()
        except Exception:
            rel = source_path.name
    else:
        rel = source_path.name
    source_text = source_path.read_text(encoding='utf-8', errors='ignore')
    source_size_bytes = len(source_text.encode('utf-8', errors='ignore'))
    source_sha = _source_sha256(source_text)

    if should_copy(source_path):
        shutil.copy2(source_path, dest_path)
        compressed_size_bytes = dest_path.stat().st_size if dest_path.exists() else source_size_bytes
        return {
            'file': rel,
            'mode': 'copied_passthrough',
            'strategy': 'copy',
            'tooling': 'raw copy',
            'fidelity': 'full',
            'compressor_status': 'copy_passthrough',
            'source_size_bytes': source_size_bytes,
            'compressed_size_bytes': compressed_size_bytes,
            'source_hash': source_sha,
            'source_sha256': source_sha,
        }

    if should_compress(source_path):
        try:
            compressed, metadata = compress_file_content_with_metadata(str(source_path), source_text)
            if str(metadata.get('fidelity') or '') == 'skeleton' and str(metadata.get('compressor_status') or '') != 'parse_failed_passthrough':
                compressed = _prepend_skeleton_header(source_path, rel, compressed)
            dest_path.write_text(compressed, encoding='utf-8')
            compressed_size_bytes = len(compressed.encode('utf-8', errors='ignore'))
            return {
                'file': rel,
                **metadata,
                'source_size_bytes': source_size_bytes,
                'compressed_size_bytes': compressed_size_bytes,
                'source_hash': source_sha,
                'source_sha256': source_sha,
            }
        except Exception as e:
            print(f"  [Error] Could not compress {source_path.name}: {e}")
            shutil.copy2(source_path, dest_path)
            compressed_size_bytes = dest_path.stat().st_size if dest_path.exists() else source_size_bytes
            return {
                'file': rel,
                'mode': 'full_due_parse_error',
                'strategy': 'copy',
                'tooling': 'raw copy',
                'note': str(e),
                'fidelity': 'full_due_parse_error',
                'compressor_status': 'parse_failed_passthrough',
                'source_size_bytes': source_size_bytes,
                'compressed_size_bytes': compressed_size_bytes,
                'source_hash': source_sha,
                'source_sha256': source_sha,
            }
    shutil.copy2(source_path, dest_path)
    compressed_size_bytes = dest_path.stat().st_size if dest_path.exists() else source_size_bytes
    return {
        'file': rel,
        'mode': 'copied_passthrough',
        'strategy': 'copy',
        'tooling': 'raw copy',
        'fidelity': 'full',
        'compressor_status': 'copy_passthrough',
        'source_size_bytes': source_size_bytes,
        'compressed_size_bytes': compressed_size_bytes,
        'source_hash': source_sha,
        'source_sha256': source_sha,
    }



def write_bloq_manifest(dest_dir: Path, source_dir: Path, records: list[dict[str, Any]]) -> None:
    rel_records = []
    for record in records:
        file_path = Path(record['file'])
        try:
            rel = file_path.relative_to(source_dir).as_posix()
        except ValueError:
            rel = file_path.as_posix()
        entry = dict(record)
        entry['file'] = rel
        rel_records.append(entry)
    rel_records.sort(key=lambda item: item['file'])
    counts = Counter(item['mode'] for item in rel_records)
    manifest = {
        'version': _repo_version(),
        'kind': 'qompressor_run_manifest',
        'capabilities': collect_runtime_capabilities(),
        'mode_counts': dict(sorted(counts.items())),
        'files': rel_records,
    }
    (dest_dir / '.bloq_manifest.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False), encoding='utf-8')



def main() -> None:
    parser = argparse.ArgumentParser(description='Qompressor - deterministic multi-language structural skeletonizer')
    parser.add_argument('source_dir', nargs='?', default='qodeyard')
    parser.add_argument('dest_dir', nargs='?', default='bloq.d')
    parser.add_argument('--capabilities', action='store_true', help='Print current native/fallback capability report and exit.')
    parser.add_argument('--capabilities-json', action='store_true', help='Print capability report as JSON and exit.')
    args = parser.parse_args()

    if args.capabilities_json:
        print(capability_report_json())
        return
    if args.capabilities:
        print(format_capability_report())
        return

    source_dir = Path(args.source_dir)
    dest_dir = Path(args.dest_dir)

    if not source_dir.exists():
        print(f"Error: Source directory '{source_dir}' not found.")
        sys.exit(1)

    cycle_num = os.environ.get('CYCLE_NUM', '?')
    print(f"--- Qompressor v{_repo_version()}: Skeletonizing {source_dir} -> {dest_dir} (Cycle {cycle_num}) ---")

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
        print(f"     [G6.5] Purged stale bloq.d/ (ensuring current-cycle freshness)")
    dest_dir.mkdir()

    file_count = 0
    records: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [
            d for d in dirs
            if d not in INFRA_DIR_NAMES and not is_generated_output_dir(Path(root) / d)
        ]
        for file in files:
            source_file = Path(root) / file
            if is_source_junk_file(source_file) or file.startswith('.'):
                continue
            rel_path = source_file.relative_to(source_dir)
            dest_file = dest_dir / rel_path
            record = process_file(source_file, dest_file, source_root=source_dir, rel_path=str(rel_path.as_posix()))
            records.append(record)
            file_count += 1

    marker_path = dest_dir / ".bloq_cycle_marker"
    marker_path.write_text(f"cycle={cycle_num}\n", encoding='utf-8')
    write_bloq_manifest(dest_dir, source_dir, records)
    mode_counts = ', '.join(f'{name}={count}' for name, count in sorted(Counter(record['mode'] for record in records).items()))
    if mode_counts:
        print(f"--- Qompressor modes: {mode_counts} ---")
    print(f"--- Qompressor v{_repo_version()}: Finished. {file_count} files processed (cycle {cycle_num}). ---")


if __name__ == "__main__":
    main()
