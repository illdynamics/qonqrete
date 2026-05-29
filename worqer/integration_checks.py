from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def normalize_file_hint(value) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if text.startswith("qodeyard/"):
        text = text[len("qodeyard/"):]
    while text.startswith("./"):
        text = text[2:]
    return text.strip()


def normalize_file_hints(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, Path)):
        values = [values]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = normalize_file_hint(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _normalize_message(issue: dict) -> str:
    return " ".join(str(issue.get("message") or issue.get("summary") or "").split())



def fingerprint_issue(issue: dict) -> str:
    if not isinstance(issue, dict):
        return ""
    source = str(issue.get("source") or issue.get("scope") or issue.get("check_type") or "unknown").strip().lower()
    message = _normalize_message(issue).lower()
    files = "|".join(sorted(normalize_file_hints(issue.get("file")) + normalize_file_hints(issue.get("files")) + normalize_file_hints(issue.get("related_files"))))
    if not message and not files:
        return ""
    return f"{source}::{message}::{files}".strip(":")



def build_issue_fingerprint_entries(issues: Iterable[dict]) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        fp = fingerprint_issue(issue)
        if not fp or fp in seen:
            continue
        seen.add(fp)
        files = sorted(set(normalize_file_hints(issue.get("file")) + normalize_file_hints(issue.get("files")) + normalize_file_hints(issue.get("related_files"))))
        build_groups = normalize_file_hints(issue.get("build_groups"))
        build_group_id = normalize_file_hint(issue.get("build_group_id"))
        if build_group_id and build_group_id not in build_groups:
            build_groups.append(build_group_id)
        scopes = normalize_file_hints(issue.get("scopes"))
        scope = normalize_file_hint(issue.get("scope"))
        if scope and scope not in scopes:
            scopes.append(scope)
        entries.append({
            "fingerprint": fp,
            "source": issue.get("source"),
            "severity": issue.get("severity"),
            "summary": issue.get("message") or issue.get("summary") or "",
            "files": files,
            "build_groups": build_groups,
            "scopes": scopes,
            "check_type": issue.get("check_type"),
        })
    return entries



def _extract_target_files_from_briq_text(text: str) -> list[str]:
    targets: list[str] = []
    for match in re.finditer(r"^Target-Files:\s*(.+)$", text, re.MULTILINE):
        values = [normalize_file_hint(item) for item in re.split(r"[,\s]+", match.group(1))]
        targets.extend([item for item in values if item])
    for match in re.finditer(r"^Primary-Deliverables:\s*(.+)$", text, re.MULTILINE):
        values = [normalize_file_hint(item) for item in re.split(r"[,\s]+", match.group(1))]
        targets.extend([item for item in values if item])
    return sorted(set(targets))



def derive_group_scope_files(
    worqspace_root: Path,
    *,
    target_files: list[str] | None = None,
    target_build_groups: list[str] | None = None,
    target_briq_refs: list[str] | None = None,
    current_build_group: str | None = None,
    current_briq_ref: str | None = None,
) -> list[str]:
    target_group_set = {str(item).strip() for item in (target_build_groups or []) if str(item).strip()}
    target_briq_set = {str(item).strip() for item in (target_briq_refs or []) if str(item).strip()}
    if current_build_group:
        target_group_set.add(str(current_build_group).strip())
    if current_briq_ref:
        target_briq_set.add(str(current_briq_ref).strip())

    files: set[str] = set(normalize_file_hints(target_files))
    planning = _load_json(worqspace_root / "planning" / "build-groups.v1.json")
    qodeyard = worqspace_root / "qodeyard"

    items = planning.get("items") or []
    briq_inventory = {item.get("briq_ref"): item for item in (planning.get("briq_inventory") or []) if item.get("briq_ref")}

    group_to_briqs: dict[str, list[str]] = {}
    for item in items:
        group_id = str(item.get("build_group_id") or "").strip()
        if not group_id:
            continue
        group_to_briqs[group_id] = [str(ref).strip() for ref in (item.get("briq_refs") or []) if str(ref).strip()]
        if target_group_set and group_id not in target_group_set:
            continue
        files.update(normalize_file_hints(item.get("target_files")))
        files.update(normalize_file_hints(item.get("primary_files")))
        build_report = _load_json(worqspace_root / "build" / "groups" / group_id / "build-report.v1.json")
        files.update(normalize_file_hints(build_report.get("files")))
        changed_scope = _load_json(worqspace_root / "build" / "groups" / group_id / "changed-files.v1.json")
        for entry in changed_scope.get("changed_files") or []:
            if isinstance(entry, dict):
                files.update(normalize_file_hints(entry.get("path")))

    for briq_ref in list(target_briq_set):
        inv = briq_inventory.get(briq_ref) or {}
        files.update(normalize_file_hints(inv.get("target_files")))
        files.update(normalize_file_hints(inv.get("primary_deliverables")))
        briq_path = worqspace_root / "briq.d"
        for candidate in sorted(briq_path.glob("*.md")):
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                continue
            if re.search(rf"^Briq-Ref:\s*{re.escape(briq_ref)}\s*$", text, re.MULTILINE):
                files.update(_extract_target_files_from_briq_text(text))
                break
        for group_id, briqs in group_to_briqs.items():
            if briq_ref in briqs:
                target_group_set.add(group_id)

    for group_id in target_group_set:
        build_report = _load_json(worqspace_root / "build" / "groups" / group_id / "build-report.v1.json")
        files.update(normalize_file_hints(build_report.get("files")))

    for rel in list(files):
        candidate = qodeyard / rel
        if candidate.exists() and candidate.is_file():
            continue
    return sorted(item for item in files if item)



def _load_task_text(worqspace_root: Path) -> str:
    task_spec = _load_json(worqspace_root / "task" / "task-spec.v1.json")
    pieces = [
        str(task_spec.get("clarified_task_body") or ""),
        str(task_spec.get("task_body") or ""),
        str(task_spec.get("goal") or ""),
        str(task_spec.get("clarification_summary") or ""),
    ]
    return "\n".join(piece for piece in pieces if piece).strip()



def _extract_exact_localstorage_keys(task_text: str) -> list[str]:
    if "localstorage" not in task_text.lower():
        return []
    keys: list[str] = []
    in_block = False
    for raw_line in task_text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if "localstorage" in lower and "exactly these keys" in lower:
            in_block = True
            continue
        if in_block:
            if not line:
                continue
            if not line.startswith("-"):
                break
            candidate = line.lstrip("-").strip().strip("`").strip()
            if candidate:
                keys.append(candidate)
    return keys



def _collect_html_ids(html: str) -> set[str]:
    return set(re.findall(r'id=["\']([^"\']+)["\']', html or ""))


def _collect_js_id_refs(js: str) -> set[str]:
    refs = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", js or ""))
    refs.update(re.findall(r"querySelector\(\s*['\"]#([^'\"]+)['\"]\s*\)", js or ""))
    refs.update(re.findall(r"closest\(\s*['\"]#([^'\"]+)['\"]\s*\)", js or ""))
    return refs


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _strip_js_comments(js: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", js or "", flags=re.DOTALL)
    return re.sub(r"//[^\n\r]*", "", without_block)


def _extract_js_const_expressions(js: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    const_exprs: dict[str, str] = {}
    object_exprs: dict[str, dict[str, str]] = {}
    for name, raw_expr in re.findall(
        r"\bconst\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(.*?);",
        js or "",
        flags=re.DOTALL,
    ):
        expr = (raw_expr or "").strip()
        if expr.startswith("{") and expr.endswith("}"):
            body = expr[1:-1]
            entries: dict[str, str] = {}
            for key_raw, value_raw in re.findall(
                r"([A-Za-z_$][A-Za-z0-9_$]*|['\"][^'\"]+['\"])\s*:\s*([^,\n}]+)",
                body,
            ):
                key = key_raw.strip().strip("'\"")
                value = (value_raw or "").strip()
                if key and value:
                    entries[key] = value
            object_exprs[name] = entries
        else:
            const_exprs[name] = expr
    return const_exprs, object_exprs


def _resolve_js_storage_key(
    expr: str,
    const_exprs: dict[str, str],
    object_exprs: dict[str, dict[str, str]],
    *,
    depth: int = 0,
    seen: set[str] | None = None,
) -> str | None:
    if depth > 8:
        return None
    text = (expr or "").strip()
    if not text:
        return None
    seen_tokens = set(seen or set())

    literal_match = re.match(r"^['\"]([^'\"]+)['\"]$", text)
    if literal_match:
        return literal_match.group(1)

    ident_match = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)$", text)
    if ident_match:
        ident = ident_match.group(1)
        if ident in seen_tokens:
            return None
        next_expr = const_exprs.get(ident)
        if next_expr is None:
            return None
        return _resolve_js_storage_key(
            next_expr,
            const_exprs,
            object_exprs,
            depth=depth + 1,
            seen=seen_tokens | {ident},
        )

    member_match = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)\.([A-Za-z_$][A-Za-z0-9_$]*)$", text)
    if member_match:
        obj_name, prop_name = member_match.group(1), member_match.group(2)
        token = f"{obj_name}.{prop_name}"
        if token in seen_tokens:
            return None
        next_expr = (object_exprs.get(obj_name) or {}).get(prop_name)
        if next_expr is None:
            return None
        return _resolve_js_storage_key(
            next_expr,
            const_exprs,
            object_exprs,
            depth=depth + 1,
            seen=seen_tokens | {token},
        )

    bracket_member_match = re.match(
        r"^([A-Za-z_$][A-Za-z0-9_$]*)\[\s*['\"]([A-Za-z_$][A-Za-z0-9_$-]*)['\"]\s*\]$",
        text,
    )
    if bracket_member_match:
        obj_name, prop_name = bracket_member_match.group(1), bracket_member_match.group(2)
        token = f"{obj_name}[{prop_name}]"
        if token in seen_tokens:
            return None
        next_expr = (object_exprs.get(obj_name) or {}).get(prop_name)
        if next_expr is None:
            return None
        return _resolve_js_storage_key(
            next_expr,
            const_exprs,
            object_exprs,
            depth=depth + 1,
            seen=seen_tokens | {token},
        )

    # v1.4.0: Support simple template literals like `${PREFIX}-key`
    template_match = re.match(r"^[`](.*?)[`]$", text)
    if template_match:
        content = template_match.group(1)
        resolved_parts = []
        last_pos = 0
        for m in re.finditer(r"\$\{(.*?)\}", content):
            resolved_parts.append(content[last_pos:m.start()])
            var_expr = m.group(1).strip()
            val = _resolve_js_storage_key(var_expr, const_exprs, object_exprs, depth=depth+1, seen=seen_tokens)
            if val is None:
                return None # Unresolvable segment
            resolved_parts.append(val)
            last_pos = m.end()
        resolved_parts.append(content[last_pos:])
        return "".join(resolved_parts)

    return None


def _collect_localstorage_keys(js: str) -> set[str]:
    source = _strip_js_comments(js or "")
    const_exprs, object_exprs = _extract_js_const_expressions(source)
    key_exprs: list[str] = []
    key_exprs.extend(
        re.findall(r"localStorage\.(?:getItem|removeItem)\(\s*([^)]+?)\s*\)", source, flags=re.DOTALL)
    )
    key_exprs.extend(
        re.findall(r"localStorage\.setItem\(\s*([^,]+?)\s*,", source, flags=re.DOTALL)
    )

    resolved: set[str] = set()
    for expr in key_exprs:
        key = _resolve_js_storage_key(expr, const_exprs, object_exprs)
        if key:
            resolved.add(key)
    return resolved



def evaluate_frontend_group_contracts(
    worqspace_root: Path,
    scope_files: list[str] | None = None,
    *,
    qodeyard_root: Path | None = None,
) -> list[dict]:
    qodeyard = Path(qodeyard_root) if qodeyard_root is not None else (worqspace_root / "qodeyard")
    scope_set = set(normalize_file_hints(scope_files)) if scope_files else set()
    scope_name_set = {Path(item).name for item in scope_set}
    
    # v1.4.0: Resolve requirements from planning artifacts
    criteria = _load_json(worqspace_root / "planning" / "completion-criteria.v1.json")
    required_files = normalize_file_hints(criteria.get("required_files", []))
    
    html_targets = [f for f in required_files if f.endswith((".html", ".htm"))]
    required_file_set = set(required_files)
    required_file_names = {Path(item).name for item in required_files}

    # Only run if relevant files are in scope
    relevant_extensions = {".html", ".htm", ".js", ".css"}
    if scope_set and not any(Path(s).suffix.lower() in relevant_extensions for s in scope_set):
        return []
    
    def _in_scope(rel_path: str) -> bool:
        rel = normalize_file_hint(rel_path)
        return not scope_set or rel in scope_set or Path(rel).name in scope_name_set

    issues: list[dict] = []
    task_text = _load_task_text(worqspace_root)
    
    all_js_files = [f for f in required_files if f.endswith(".js")]
    all_css_files = [f for f in required_files if f.endswith(".css")]

    for html_rel in html_targets:
        html_path = qodeyard / html_rel
        if not html_path.exists():
            continue
        
        html = _read_text(html_path)
        local_scripts = [normalize_file_hint(s) for s in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)]
        local_styles = [normalize_file_hint(s) for s in re.findall(r"<link[^>]+href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)]
        
        for ref in local_scripts + local_styles:
            if ref.startswith(("http://", "https://", "//")):
                continue
            ref_rel = normalize_file_hint(str((Path(html_rel).parent / ref)))
            if not (html_path.parent / ref).exists():
                # Scoped interleaved checks must not force cross-briq files
                # that are outside the current write scope (e.g. index.html
                # references app.js which hasn't been created yet by a later
                # briq). Defer those to the full deterministic contract/
                # harness validation pass. Required files that are known from
                # completion criteria are also deferred.
                if scope_set:
                    if not _in_scope(ref_rel):
                        continue
                    ref_name = Path(ref_rel).name
                    if ref_rel in required_file_set or ref_name in required_file_names:
                        continue
                issues.append({
                    "source": "frontend_contract",
                    "severity": "error",
                    "scope": "frontend_contract",
                    "message": f"{html_rel} references missing local file: {ref}",
                    "files": [html_rel],
                })

        # If JS/CSS files are required, ensure the primary HTML references them.
        if len(html_targets) == 1 and not scope_set:
            for js_rel in all_js_files:
                if js_rel not in local_scripts and Path(js_rel).name not in local_scripts:
                    issues.append({
                        "source": "frontend_contract",
                        "severity": "error",
                        "scope": "frontend_contract",
                        "message": f"{html_rel} does not reference required local script {js_rel}",
                        "files": [html_rel, js_rel],
                    })
            for css_rel in all_css_files:
                if css_rel not in local_styles and Path(css_rel).name not in local_styles:
                    issues.append({
                        "source": "frontend_contract",
                        "severity": "error",
                        "scope": "frontend_contract",
                        "message": f"{html_rel} does not reference required local stylesheet {css_rel}",
                        "files": [html_rel, css_rel],
                    })

        # Content/Behavior validation
        html_ids = _collect_html_ids(html)
        for js_rel in local_scripts:
            js_path = qodeyard / js_rel
            if not js_path.exists(): continue
            js = _read_text(js_path)
            js_ids = _collect_js_id_refs(js)
            missing_ids = sorted(js_ids - html_ids)
            if missing_ids:
                issues.append({
                    "source": "frontend_contract",
                    "severity": "error",
                    "scope": "frontend_contract",
                    "message": f"{js_rel} references missing DOM ids in {html_rel}: {', '.join(missing_ids)}",
                    "files": [js_rel, html_rel],
                })
            if "addEventListener" not in js and "onclick" not in html.lower():
                issues.append({
                    "source": "frontend_contract",
                    "severity": "warning",
                    "scope": "frontend_contract",
                    "message": f"{js_rel} appears to lack interactive event handlers",
                    "files": [js_rel],
                })

    storage_keys = _extract_exact_localstorage_keys(task_text)
    if storage_keys:
        used_keys = set()
        js_scope = all_js_files
        if scope_set:
            js_scope = [item for item in all_js_files if _in_scope(item)]
        # Avoid impossible cross-briq failures: only enforce storage-key
        # completeness in full-scope validation runs.
        if scope_set and not js_scope:
            js_scope = []
        for js_rel in js_scope:
            js_path = qodeyard / js_rel
            if js_path.exists():
                used_keys.update(_collect_localstorage_keys(_read_text(js_path)))
        
        scope_covers_required_js = True
        if scope_set and all_js_files:
            scope_covers_required_js = all(_in_scope(js_rel) for js_rel in all_js_files)

        missing_keys = [key for key in storage_keys if key not in used_keys]
        if missing_keys and (not scope_set or scope_covers_required_js):
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"Required localStorage keys missing from JS implementation: {', '.join(missing_keys)}",
                "files": all_js_files[:1] or html_targets[:1],
            })

    return issues


def _collect_python_symbols(module_text: str) -> set[str]:
    symbols = set()
    for pattern in [r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", r"^def\s+([A-Za-z_][A-Za-z0-9_]*)", r"^([A-Za-z_][A-Za-z0-9_]*)\s*="]:
        symbols.update(re.findall(pattern, module_text or "", flags=re.MULTILINE))
    return symbols


def evaluate_python_fastapi_integration(
    worqspace_root: Path,
    scope_files: list[str] | None = None,
    *,
    qodeyard_root: Path | None = None,
) -> list[dict]:
    qodeyard = Path(qodeyard_root) if qodeyard_root is not None else (worqspace_root / "qodeyard")
    scope_set = set(normalize_file_hints(scope_files)) if scope_files else set()

    python_files = [normalize_file_hint(path.relative_to(qodeyard)) for path in qodeyard.rglob("*.py") if path.is_file()]
    if scope_set:
        python_files = [item for item in python_files if item in scope_set or Path(item).name in {Path(s).name for s in scope_set}]
    if not python_files:
        return []

    module_texts = {rel: _read_text(qodeyard / rel) for rel in python_files}
    symbol_index = {rel: _collect_python_symbols(text) for rel, text in module_texts.items()}
    issues: list[dict] = []

    # Local Import Integrity
    for rel, text in module_texts.items():
        # Match both 'import x' and 'from x import y'
        # This is a bit redundant with Qualifier but provides ConstruQtor with immediate integration feedback
        for match in re.finditer(r"^from\s+([A-Za-z0-9_./]+)\s+import\s+(.+)$", text, flags=re.MULTILINE):
            module_name = match.group(1).replace(".", "/")
            if module_name.startswith((".", "/")):
                continue
            
            import_path = normalize_file_hint(f"{module_name}.py")
            if import_path not in symbol_index: continue
            
            imported_names = [part.strip().split(" as ")[0].strip() for part in match.group(2).split(",")]
            missing = [name for name in imported_names if name and name != "*" and name not in symbol_index.get(import_path, set())]
            if missing:
                issues.append({
                    "source": "python_integration",
                    "severity": "error",
                    "scope": "python_integration",
                    "message": f"{rel} imports missing local symbols from {import_path}: {', '.join(missing)}",
                    "files": [rel, import_path],
                })

    return issues


def collect_scope_validation_issues(
    worqspace_root: Path,
    *,
    scope_files: list[str] | None = None,
    target_build_groups: list[str] | None = None,
    qodeyard_root: Path | None = None,
) -> list[dict]:
    del target_build_groups
    issues: list[dict] = []
    issues.extend(
        evaluate_frontend_group_contracts(
            worqspace_root,
            scope_files=scope_files,
            qodeyard_root=qodeyard_root,
        )
    )
    issues.extend(
        evaluate_python_fastapi_integration(
            worqspace_root,
            scope_files=scope_files,
            qodeyard_root=qodeyard_root,
        )
    )
    return issues
