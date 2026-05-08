from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


FULL_HOTSET = "full_hotset"
FULL_NEIGHBOR = "full_neighbor"
SKELETON = "skeleton"
QONTEXT = "qontext"
CACHED_STABLE = "cached_stable"
MISSING_NEW_FILE_TARGET = "missing_new_file_target"


TRUTHY_VALUES = {"1", "true", "yes", "on"}


@dataclass

@dataclass
class QacheValidationResult:
    cached_stable_allowed: bool
    hotset_allowed: bool
    valid: bool
    reason: str
    manifest: dict | None = None

@dataclass
class ContextBundleItem:
    rel_path: str
    actual_path: str | None
    fidelity: str
    editable: bool
    reason: str
    source: str
    source_hash: str | None = None
    source_size_bytes: int | None = None


def _normalize_rel(value: str | None) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("qodeyard/"):
        text = text[len("qodeyard/") :]
    return text


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUTHY_VALUES


def get_context_strategy_config(config: dict[str, Any] | None, is_repair_pass: bool = False) -> dict[str, Any]:
    cfg = config or {}
    # Top-level new shape
    if isinstance(cfg.get("context_strategy"), dict):
        strategy = dict(cfg["context_strategy"])
        if "normal" not in strategy:
            strategy["normal"] = "hybrid_fidelity"
        if "repair" not in strategy:
            strategy["repair"] = "repair_truth"
        return strategy

    # Fallback to old shape
    options = cfg.get("options") or {}
    legacy_val = options.get("context_strategy")
    if not legacy_val:
        legacy_val = cfg.get("context_strategy")

    val_str = str(legacy_val).strip() if legacy_val and isinstance(legacy_val, str) else ""
    return {
        "normal": val_str if val_str else "hybrid_fidelity",
        "repair": "repair_truth"
    }


def _inside(parent: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _safe_read(path: Path, max_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated]"
    return text


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def _file_size(path: Path) -> int | None:
    try:
        return int(path.stat().st_size)
    except Exception:
        return None


def _collect_qontext_docs(qontext_path: Path) -> list[dict]:
    docs: list[dict] = []
    if not qontext_path.is_dir():
        return docs
    for yaml_path in sorted(qontext_path.rglob("*.q.yaml")):
        try:
            payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not payload.get("file_path"):
            rel = _normalize_rel(str(yaml_path.relative_to(qontext_path)).replace(".q.yaml", ""))
            payload["file_path"] = rel
        docs.append(payload)
    return docs


def _build_qontext_index(qontext_docs: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    by_file: dict[str, dict] = {}
    module_to_file: dict[str, str] = {}
    for doc in qontext_docs:
        rel = _normalize_rel(doc.get("file_path"))
        if not rel:
            continue
        by_file[rel] = doc
        module = str(doc.get("module") or "").strip()
        if module:
            module_to_file[module] = rel
    return by_file, module_to_file


def _resolve_hint_to_files(
    hint: str,
    *,
    known_files: set[str],
    module_to_file: dict[str, str],
) -> set[str]:
    resolved: set[str] = set()
    if not hint:
        return resolved
    norm = _normalize_rel(hint)
    if norm in known_files:
        resolved.add(norm)
    if norm in module_to_file:
        resolved.add(module_to_file[norm])
    for module_name, rel in module_to_file.items():
        if module_name.endswith(f".{norm}") or module_name == norm or norm.startswith(f"{module_name}."):
            resolved.add(rel)
    if not resolved and "/" not in norm:
        for rel in known_files:
            if Path(rel).name == norm:
                resolved.add(rel)
    return resolved


def _related_sets_from_qontext(
    *,
    qontext_docs: list[dict],
    seed_files: list[str],
    depth: int = 2,
) -> tuple[set[str], set[str]]:
    by_file, module_to_file = _build_qontext_index(qontext_docs)
    known_files = set(by_file.keys())
    seeds = {_normalize_rel(v) for v in seed_files if _normalize_rel(v)}
    direct: set[str] = set()
    indirect: set[str] = set()

    def _neighbors(file_rel: str) -> set[str]:
        doc = by_file.get(file_rel)
        if not doc:
            return set()
        out: set[str] = set()
        deps = doc.get("dependencies", []) or []
        inbound = doc.get("inbound_refs", []) or []
        for raw in list(deps) + list(inbound):
            for rel in _resolve_hint_to_files(str(raw), known_files=known_files, module_to_file=module_to_file):
                out.add(rel)
        out.discard(file_rel)
        return out

    for seed in seeds:
        direct.update(_neighbors(seed))

    if depth >= 2:
        for rel in list(direct):
            indirect.update(_neighbors(rel))
        indirect -= direct
        indirect -= seeds

    direct -= seeds
    return direct, indirect


def build_context_bundle(
    *,
    qodeyard_path: Path,
    bloq_path: Path,
    qontext_path: Path,
    editable_targets: list[str],
    repair_targets: list[str],
    use_qompressor: bool,
    use_qontextor: bool,
    context_strategy: str,
    max_neighbor_full_chars: int = 90000,
    max_full_neighbors: int = 24,
    max_indirect: int = 40,
    repair_level: int | None = None,
) -> list[ContextBundleItem]:
    editable_set = {_normalize_rel(v) for v in editable_targets if _normalize_rel(v)}
    repair_set = {_normalize_rel(v) for v in repair_targets if _normalize_rel(v)}
    all_targets = sorted(editable_set | repair_set)
    effective_neighbor_full_chars = max_neighbor_full_chars
    effective_max_full_neighbors = max_full_neighbors
    effective_max_indirect = max_indirect
    if context_strategy == "repair_truth" and repair_level is not None:
        try:
            level = max(1, min(4, int(repair_level)))
        except Exception:
            level = 1
        if level <= 1:
            effective_neighbor_full_chars = 0
            effective_max_full_neighbors = 0
            effective_max_indirect = min(max_indirect, 12)
        elif level == 2:
            effective_max_full_neighbors = min(max_full_neighbors, 12)
            effective_max_indirect = min(max_indirect, 24)
        elif level == 3:
            effective_max_full_neighbors = max(max_full_neighbors, 24)
            effective_max_indirect = max(max_indirect, 40)
        else:
            effective_neighbor_full_chars = max(max_neighbor_full_chars, 180000)
            effective_max_full_neighbors = max(max_full_neighbors, 64)
            effective_max_indirect = max(max_indirect, 100)

    qontext_docs = _collect_qontext_docs(qontext_path) if use_qontextor else []
    direct_neighbors, indirect_neighbors = _related_sets_from_qontext(
        qontext_docs=qontext_docs,
        seed_files=all_targets,
        depth=2,
    )

    bundle: list[ContextBundleItem] = []
    emitted = set()

    def _emit(
        rel_path: str,
        *,
        actual_path: Path | None,
        fidelity: str,
        editable: bool,
        reason: str,
        source: str,
    ) -> None:
        key = (rel_path, fidelity, source, editable)
        if key in emitted:
            return
        emitted.add(key)
        bundle.append(
            ContextBundleItem(
                rel_path=rel_path,
                actual_path=str(actual_path) if actual_path else None,
                fidelity=fidelity,
                editable=editable,
                reason=reason,
                source=source,
                source_hash=_sha256_file(actual_path) if actual_path and actual_path.exists() else None,
                source_size_bytes=_file_size(actual_path) if actual_path and actual_path.exists() else None,
            )
        )

    # Editable + repair hotset must remain full qodeyard context.
    for rel in all_targets:
        qode_path = qodeyard_path / rel
        reason = "repair_target" if rel in repair_set else "briq_target"
        if qode_path.exists():
            _emit(
                rel,
                actual_path=qode_path,
                fidelity=FULL_HOTSET,
                editable=True,
                reason=reason,
                source="qodeyard",
            )
            continue
        # Missing-file repair target.
        _emit(
            rel,
            actual_path=qode_path,
            fidelity=MISSING_NEW_FILE_TARGET,
            editable=True,
            reason="new_file_target",
            source="qodeyard",
        )
        # Include nearest existing package/file context for missing file creation.
        parent = qode_path.parent
        for candidate in (
            parent / "__init__.py",
            parent / "index.ts",
            parent / "index.js",
            parent / "README.md",
        ):
            try:
                rel_candidate = _normalize_rel(str(candidate.relative_to(qodeyard_path)))
            except Exception:
                continue
            if not rel_candidate or not candidate.exists():
                continue
            _emit(
                rel_candidate,
                actual_path=candidate,
                fidelity=FULL_NEIGHBOR,
                editable=False,
                reason="new_file_parent_context",
                source="qodeyard",
            )

    full_neighbor_count = 0
    for rel in sorted(direct_neighbors):
        if rel in all_targets:
            continue
        qode_path = qodeyard_path / rel
        if not qode_path.exists():
            continue
        size = int(qode_path.stat().st_size) if qode_path.exists() else 0
        if size <= effective_neighbor_full_chars and full_neighbor_count < effective_max_full_neighbors:
            _emit(
                rel,
                actual_path=qode_path,
                fidelity=FULL_NEIGHBOR,
                editable=False,
                reason="direct_dependency",
                source="qodeyard",
            )
            full_neighbor_count += 1
        else:
            if use_qompressor:
                skeleton_path = bloq_path / rel
                if skeleton_path.exists():
                    _emit(
                        rel,
                        actual_path=skeleton_path,
                        fidelity=SKELETON,
                        editable=False,
                        reason="direct_dependency_large",
                        source="bloq.d",
                    )
            if use_qontextor:
                qontext_file = qontext_path / f"{rel}.q.yaml"
                if qontext_file.exists():
                    _emit(
                        rel,
                        actual_path=qontext_file,
                        fidelity=QONTEXT,
                        editable=False,
                        reason="direct_dependency_graph",
                        source="qontext.d",
                    )

    for rel in sorted(indirect_neighbors)[:effective_max_indirect]:
        if rel in all_targets:
            continue
        if use_qompressor:
            skeleton_path = bloq_path / rel
            if skeleton_path.exists():
                _emit(
                    rel,
                    actual_path=skeleton_path,
                    fidelity=SKELETON,
                    editable=False,
                    reason="indirect_dependency",
                    source="bloq.d",
                )
        if use_qontextor:
            qontext_file = qontext_path / f"{rel}.q.yaml"
            if qontext_file.exists():
                _emit(
                    rel,
                    actual_path=qontext_file,
                    fidelity=QONTEXT,
                    editable=False,
                    reason="indirect_dependency_graph",
                    source="qontext.d",
                )

    # In repair_truth mode, enrich with validation scope file context.
    if context_strategy == "repair_truth":
        for rel in sorted(repair_set):
            qode_path = qodeyard_path / rel
            if qode_path.exists():
                _emit(
                    rel,
                    actual_path=qode_path,
                    fidelity=FULL_HOTSET,
                    editable=True,
                    reason="repair_truth",
                    source="qodeyard",
                )

    return bundle


def validate_bundle_invariants(
    *,
    bundle: list[ContextBundleItem],
    qodeyard_path: Path,
    repair_targets: list[str],
    bloq_path: Path | None = None,
    qontext_path: Path | None = None,
) -> None:
    bloq_root = bloq_path or (qodeyard_path.parent / "bloq.d")
    qontext_root = qontext_path or (qodeyard_path.parent / "qontext.d")
    for item in bundle:
        if item.editable and item.fidelity not in {FULL_HOTSET, MISSING_NEW_FILE_TARGET}:
            raise RuntimeError(
                f"Invalid context bundle: editable file {item.rel_path} cannot use fidelity {item.fidelity}."
            )
        if item.editable and item.source != "qodeyard":
            raise RuntimeError(
                f"Invalid context bundle: editable file {item.rel_path} must source from qodeyard, got {item.source}."
            )
        if item.fidelity == SKELETON and item.editable:
            raise RuntimeError(
                f"Invalid context bundle: skeleton file {item.rel_path} cannot be editable."
            )
        if item.actual_path:
            actual = Path(item.actual_path)
            expected_root = {
                "qodeyard": qodeyard_path,
                "bloq.d": bloq_root,
                "qontext.d": qontext_root,
            }.get(item.source)
            if expected_root is None:
                raise RuntimeError(
                    f"Invalid context bundle: unknown source root {item.source} for {item.rel_path}."
                )
            if not _inside(expected_root, actual):
                raise RuntimeError(
                    f"Invalid context bundle: {item.source} context escapes root for {item.rel_path}."
                )

    by_rel: dict[str, list[ContextBundleItem]] = {}
    for item in bundle:
        by_rel.setdefault(item.rel_path, []).append(item)

    for rel in {_normalize_rel(v) for v in repair_targets if _normalize_rel(v)}:
        qode_path = qodeyard_path / rel
        options = by_rel.get(rel, [])
        if not options:
            raise RuntimeError(
                f"Repair target {rel} is absent from the context bundle."
            )
        if not qode_path.exists():
            if not any(opt.fidelity == MISSING_NEW_FILE_TARGET and opt.reason == "new_file_target" for opt in options):
                raise RuntimeError(
                    f"Missing repair target {rel} must be marked as new_file_target."
                )
            continue
        if not any(
            opt.source == "qodeyard"
            and opt.fidelity == FULL_HOTSET
            for opt in options
        ):
            raise RuntimeError(
                f"Repair target {rel} must include full editable qodeyard context."
            )


def build_bundle_prompt_sections(
    *,
    bundle: list[ContextBundleItem],
    qache_dir: Path,
    max_chars_per_file: int = 120000,
    include_cached_stable: bool = True,
) -> list[dict[str, Any]]:
    cached_payload_path = qache_dir / "cached_payload.txt"
    sections: list[dict[str, Any]] = []

    if include_cached_stable and cached_payload_path.exists():
        cached_text = _safe_read(cached_payload_path, max_chars=600000)
        if cached_text.strip():
            sections.append(
                {
                    "label": "cached_stable_context",
                    "content": (
                        "CACHED STABLE CONTEXT\n"
                        "Background only. If this conflicts with full source context, full source wins.\n\n"
                        + cached_text
                        + "\n"
                    ),
                    "required": False,
                    "loss_policy": "summarizable",
                    "section_type": "cached_stable_context",
                    "source_files": [str(cached_payload_path)],
                }
            )

    structural_blocks: list[str] = []
    readonly_blocks: list[str] = []
    editable_blocks: list[str] = []

    for item in sorted(bundle, key=lambda x: (x.fidelity, x.rel_path, x.source)):
        path_obj = Path(item.actual_path) if item.actual_path else None
        if item.fidelity in {SKELETON, QONTEXT}:
            text = _safe_read(path_obj, max_chars=max_chars_per_file) if path_obj and path_obj.exists() else ""
            if text:
                structural_blocks.append(
                    f"FILE: {item.rel_path}\nSOURCE: {item.source}\nFIDELITY: {item.fidelity}\nREASON: {item.reason}\n```\n{text}\n```"
                )
            continue

        if item.fidelity == FULL_NEIGHBOR and path_obj and path_obj.exists():
            text = _safe_read(path_obj, max_chars=max_chars_per_file)
            readonly_blocks.append(
                f"FILE: {item.rel_path}\nSOURCE: qodeyard\nFIDELITY: full_neighbor\nREASON: {item.reason}\n```\n{text}\n```"
            )
            continue

        if item.fidelity in {FULL_HOTSET, MISSING_NEW_FILE_TARGET}:
            if path_obj and path_obj.exists():
                text = _safe_read(path_obj, max_chars=max_chars_per_file)
                editable_blocks.append(
                    f"FILE: {item.rel_path}\nSOURCE: qodeyard\nFIDELITY: {item.fidelity}\nREASON: {item.reason}\n```\n{text}\n```"
                )
            else:
                editable_blocks.append(
                    f"FILE: {item.rel_path}\nSOURCE: qodeyard\nFIDELITY: {MISSING_NEW_FILE_TARGET}\nREASON: new_file_target\nMISSING: true\n"
                )

    if structural_blocks:
        sections.append(
            {
                "label": "structural_context",
                "content": (
                    "STRUCTURAL CONTEXT\n"
                    "Skeletons and qontexts only. Navigation only. Never copy this into qodeyard.\n\n"
                    + "\n\n".join(structural_blocks)
                    + "\n"
                ),
                "required": False,
                "loss_policy": "summarizable",
                "section_type": "structural_context",
            }
        )

    if readonly_blocks:
        sections.append(
            {
                "label": "full_readonly_context",
                "content": (
                    "FULL READONLY CONTEXT\n"
                    "Authoritative source. Do not change unless necessary.\n\n"
                    + "\n\n".join(readonly_blocks)
                    + "\n"
                ),
                "required": False,
                "loss_policy": "summarizable",
                "section_type": "full_readonly_context",
            }
        )

    if editable_blocks:
        sections.append(
            {
                "label": "full_editable_context",
                "content": (
                    "FULL EDITABLE CONTEXT\n"
                    "Authoritative source. These files may be changed.\n\n"
                    + "\n\n".join(editable_blocks)
                    + "\n"
                ),
                "required": True,
                "loss_policy": "preserve",
                "section_type": "full_editable_context",
            }
        )

    return sections


def write_context_bundle_manifest(
    *,
    qache_dir: Path,
    provider: str,
    model: str = "",
    cache_backend: str,
    cache_backend_reason: str = "",
    pass_kind: str,
    repair_mode: bool,
    bundle: list[ContextBundleItem],
    cycle_num: str = "",
    build_pass_index: int = 0,
    repair_pass_index: int = 0,
    target_files: list[str] | None = None,
    repair_targets: list[str] | None = None,
    qodeyard_path: Path | None = None,
) -> Path:
    qache_dir.mkdir(parents=True, exist_ok=True)

    import hashlib, datetime

    source_hashes: dict[str, str] = {}
    if qodeyard_path:
        for item in bundle:
            if item.source == "qodeyard" and item.fidelity in {FULL_HOTSET, FULL_NEIGHBOR}:
                try:
                    fpath = qodeyard_path / item.rel_path
                    if fpath.exists():
                        source_hashes[item.rel_path] = hashlib.sha256(
                            fpath.read_bytes()
                        ).hexdigest()
                except Exception:
                    pass

    # Compute context_hash over stable cached content only
    context_hash_input = json.dumps(
        {
            "provider": str(provider or "").strip().lower(),
            "cache_backend": str(cache_backend or "").strip() or "local_only",
            "pass_kind": pass_kind,
            "repair_mode": bool(repair_mode),
            "cycle_num": str(cycle_num),
            "source_hashes": source_hashes,
        },
        sort_keys=True,
    )
    context_hash = hashlib.sha256(context_hash_input.encode()).hexdigest()

    payload = {
        "schema_version": "context_bundle_manifest.v1",
        "provider": str(provider or "").strip().lower(),
        "model": str(model or "").strip(),
        "cache_backend": str(cache_backend or "").strip() or "local_only",
        "cache_backend_reason": str(cache_backend_reason or "").strip(),
        "pass_kind": pass_kind,
        "repair_mode": bool(repair_mode),
        "cycle_num": str(cycle_num),
        "build_pass_index": int(build_pass_index or 0),
        "repair_pass_index": int(repair_pass_index or 0),
        "target_files": sorted(set(target_files or [])),
        "repair_targets": sorted(set(repair_targets or [])),
        "source_hashes": source_hashes,
        "context_hash": context_hash,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files": [asdict(item) for item in bundle],
    }
    out_path = qache_dir / "context_bundle_manifest.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def validate_qache_manifest_for_construqtor(
    *,
    qache_dir: Path,
    provider: str,
    model: str,
    pass_kind: str,
    repair_mode: bool,
    cycle_num: str,
    expected_targets: list[str],
    qodeyard_path: Path,
    expected_repair_targets: list[str] | None = None,
    build_pass_index: int | str | None = None,
    repair_pass_index: int | str | None = None,
    require_hotset_payload: bool = True,
) -> QacheValidationResult:
    """Validate that qache payloads match the current ConstruQtor pass.

    Returns QacheValidationResult containing details on what can be reused.
    """
    manifest_path = qache_dir / "context_bundle_manifest.json"
    if not manifest_path.exists():
        return QacheValidationResult(False, False, False, "manifest_missing")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return QacheValidationResult(False, False, False, "manifest_invalid_json")

    # Check schema version
    if manifest.get("schema_version") != "context_bundle_manifest.v1":
        return QacheValidationResult(False, False, False, "manifest_schema_mismatch", manifest)

    # Check provider and pass metadata
    if str(manifest.get("provider") or "").strip().lower() != str(provider or "").strip().lower():
        return QacheValidationResult(False, False, False, "provider_mismatch", manifest)
    manifest_model = str(manifest.get("model") or "").strip()
    if manifest_model and str(model or "").strip() and manifest_model != str(model or "").strip():
        return QacheValidationResult(False, False, False, "model_mismatch", manifest)

    # Cycle must match (same global iteration)
    manifest_cycle = str(manifest.get("cycle_num") or "")
    current_cycle = str(cycle_num or "")
    if manifest_cycle != current_cycle:
        return QacheValidationResult(False, False, False, "cycle_mismatch", manifest)

    # Pass kind must match
    if str(manifest.get("pass_kind") or "").strip().lower() != str(pass_kind or "").strip().lower():
        return QacheValidationResult(False, False, False, "pass_kind_mismatch", manifest)

    if bool(manifest.get("repair_mode")) != bool(repair_mode):
        return QacheValidationResult(False, False, False, "repair_mode_mismatch", manifest)

    if build_pass_index is not None and str(build_pass_index) != "":
        try:
            if int(manifest.get("build_pass_index") or 0) != int(build_pass_index):
                return QacheValidationResult(False, False, False, "build_pass_index_mismatch", manifest)
        except Exception:
            return QacheValidationResult(False, False, False, "build_pass_index_error", manifest)
    if repair_pass_index is not None and str(repair_pass_index) != "":
        try:
            if int(manifest.get("repair_pass_index") or 0) != int(repair_pass_index):
                return QacheValidationResult(False, False, False, "repair_pass_index_mismatch", manifest)
        except Exception:
            return QacheValidationResult(False, False, False, "repair_pass_index_error", manifest)

    # Check source hashes for full_hotset/full_neighbor files still match qodeyard
    source_hashes = manifest.get("source_hashes") or {}
    if source_hashes:
        import hashlib
        for rel_path, expected_hash in source_hashes.items():
            fpath = qodeyard_path / _normalize_rel(str(rel_path))
            if fpath.exists():
                try:
                    actual_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    if actual_hash != expected_hash:
                        return QacheValidationResult(False, False, False, f"source_hash_mismatch:{rel_path}", manifest)
                except Exception:
                    return QacheValidationResult(False, False, False, f"source_hash_error:{rel_path}", manifest)
            else:
                return QacheValidationResult(False, False, False, f"source_missing:{rel_path}", manifest)

    # Check target files match
    manifest_targets = set(_normalize_rel(str(t)) for t in (manifest.get("target_files") or []) if _normalize_rel(str(t)))
    current_targets = set(_normalize_rel(str(t)) for t in (expected_targets or []) if _normalize_rel(str(t)))
    
    # Superset target match allows cached_stable context
    cached_stable_allowed = manifest_targets.issuperset(current_targets)
    
    # Exact target match for hotset_allowed
    hotset_allowed = (manifest_targets == current_targets)

    if expected_repair_targets is not None:
        manifest_repairs = set(_normalize_rel(str(t)) for t in (manifest.get("repair_targets") or []) if _normalize_rel(str(t)))
        current_repairs = set(_normalize_rel(str(t)) for t in (expected_repair_targets or []) if _normalize_rel(str(t)))
        if manifest_repairs != current_repairs:
            cached_stable_allowed = False
            hotset_allowed = False

    if not (qache_dir / "cached_payload.txt").exists():
        cached_stable_allowed = False

    if require_hotset_payload and not (qache_dir / "hotset_payload.txt").exists():
        hotset_allowed = False

    valid = cached_stable_allowed or hotset_allowed
    reason = "valid" if valid else "targets_mismatch_or_payload_missing"

    return QacheValidationResult(
        cached_stable_allowed=cached_stable_allowed,
        hotset_allowed=hotset_allowed,
        valid=valid,
        reason=reason,
        manifest=manifest,
    )


def gemini_explicit_cache_available() -> bool:
    """Return True if a real Gemini CachedContent adapter exists."""
    return False

def resolve_qontrabender_cache_backend(
    *,
    provider: str,
    provider_cache_cfg: dict[str, Any] | None,
) -> str:
    cfg = provider_cache_cfg or {}
    provider_l = str(provider or "").strip().lower()
    remote_enabled = _is_truthy(cfg.get("enabled", True))
    if not remote_enabled:
        return "disabled"

    if provider_l in {"gemini", "google"}:
        if _is_truthy(cfg.get("gemini_explicit_enabled")) and gemini_explicit_cache_available():
            return "gemini_explicit"
        return "stable_prefix_auto"
    if provider_l == "anthropic":
        if _is_truthy(cfg.get("anthropic_cache_control_enabled", True)):
            return "anthropic_cache_control"
        return "stable_prefix_auto"
    if provider_l == "openai":
        if not _is_truthy(cfg.get("openai_stable_prefix_enabled", True)):
            return "local_only"
        return "stable_prefix_auto"
    if provider_l == "deepseek":
        if not _is_truthy(cfg.get("deepseek_stable_prefix_enabled", True)):
            return "local_only"
        return "stable_prefix_auto"
    if provider_l == "codeseeq":
        if not _is_truthy(cfg.get("deepseek_stable_prefix_enabled", True)):
            return "local_only"
        return "stable_prefix_auto"
    if provider_l in {"local", "mlx", "llama-cpp"}:
        return "local_only"
    if provider_l in {"openrouter", "qwen", "venice"}:
        if not _is_truthy(cfg.get("openai_compatible_stable_prefix_enabled", True)):
            return "local_only"
        return "stable_prefix_auto"
    return "local_only"
