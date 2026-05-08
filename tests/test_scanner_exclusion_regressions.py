from __future__ import annotations

from pathlib import Path
from unittest import mock

import path_hygiene
import qompressor
import qontextor
import qontrabender
from qualifier import runner as qualifier_runner
from smoqetester import runner as smoqetester_runner


def _write(path: Path, text: str = "print('junk')\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_repo(root: Path, junk_count: int = 5) -> Path:
    _write(root / "app.py", "print('ok')\n")
    junk_roots = [
        root / ".git" / "objects",
        root / ".qonqrete" / ".git" / "objects",
        root / ".gradle" / "8.5",
        root / ".validation-env-cache",
        root / ".pytest_cache",
        root / ".ruff_cache",
        root / "node_modules" / "pkg",
        root / "__pycache__",
        root / "vscode-extension" / "out",
    ]
    for index in range(junk_count):
        for junk_root in junk_roots:
            _write(junk_root / f"junk{index}.py")
            _write(junk_root / f"junk{index}.pyc", b"\0".decode("latin1"))
        _write(root / "__pycache__" / f"app{index}.cpython-311.pyc", b"\0".decode("latin1"))
        _write(root / f"._appledouble{index}.py")
    _write(root / ".DS_Store", "mac metadata\n")
    return root


def _relative_set(root: Path, files: list[Path] | tuple[Path, ...] | set[Path]) -> set[str]:
    return {path.relative_to(root).as_posix() for path in files}


def _assert_only_real_source(root: Path, files: list[Path] | tuple[Path, ...] | set[Path]) -> None:
    rels = _relative_set(root, files)
    assert "app.py" in rels
    assert not any(".qonqrete/.git" in rel for rel in rels)
    assert not any(".git/" in rel for rel in rels)
    assert not any("__pycache__" in rel for rel in rels)
    assert not any(rel.endswith(".pyc") for rel in rels)
    assert not any(".gradle/" in rel for rel in rels)
    assert not any("node_modules/" in rel for rel in rels)
    assert not any("vscode-extension/out/" in rel for rel in rels)
    assert not any("/._" in f"/{rel}" for rel in rels)


def test_shared_source_walker_excludes_cache_generated_and_plugin_build_dirs(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path / "qodeyard")

    _assert_only_real_source(root, list(path_hygiene.iter_source_files(root)))


def test_validation_scanners_do_not_inspect_qonqrete_git_pycache_or_pyc(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path / "qodeyard")

    _assert_only_real_source(root, list(qualifier_runner._iter_source_files(root)))
    _assert_only_real_source(root, list(smoqetester_runner._iter_source_files(root)))
    _assert_only_real_source(root, list(qontextor._iter_processable_files(root)))


def test_qompressor_main_prunes_cache_generated_and_plugin_build_dirs(tmp_path: Path, monkeypatch) -> None:
    source = _fixture_repo(tmp_path / "qodeyard")
    dest = tmp_path / "bloq.d"
    monkeypatch.setattr(qompressor.sys, "argv", ["qompressor.py", str(source), str(dest)])

    qompressor.main()

    generated = {path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file()}
    assert "app.py" in generated
    assert ".bloq_manifest.yaml" in generated
    assert not any(".git/" in rel or ".qonqrete/.git" in rel for rel in generated)
    assert not any("__pycache__" in rel or rel.endswith(".pyc") for rel in generated)
    assert not any(".gradle/" in rel or "node_modules/" in rel for rel in generated)
    assert not any("vscode-extension/out/" in rel for rel in generated)


def test_qontrabender_subprocess_probe_count_is_bounded_for_junk_heavy_repo(tmp_path: Path) -> None:
    root = tmp_path / "worqspace"
    qodeyard = _fixture_repo(root / "qodeyard", junk_count=40)

    with mock.patch.object(qontrabender.subprocess, "run") as run:
        qb = qontrabender.Qontrabender(
            root,
            qodeyard_path=qodeyard,
            bloq_path=root / "bloq.d",
            qontext_path=root / "qontext.d",
            qache_path=root / "qache.d",
        )
        decisions = qb.analyze_files()

    assert [decision.path for decision in decisions] == ["app.py"]
    assert run.call_count <= 1
