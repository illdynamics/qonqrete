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



def evaluate_frontend_group_contracts(worqspace_root: Path, scope_files: list[str] | None = None) -> list[dict]:
    qodeyard = worqspace_root / "qodeyard"
    scope_set = set(normalize_file_hints(scope_files)) if scope_files else set()
    html_path = qodeyard / "index.html"
    js_path = qodeyard / "app.js"
    css_path = qodeyard / "styles.css"
    html = _read_text(html_path)
    js = _read_text(js_path)
    task_text = _load_task_text(worqspace_root)

    if scope_set and not ({"index.html", "app.js", "styles.css"} & scope_set):
        return []

    issues: list[dict] = []
    if html:
        local_scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        local_styles = re.findall(r"<link[^>]+href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        missing_script_refs = [ref for ref in local_scripts if not ref.startswith(("http://", "https://")) and not (qodeyard / normalize_file_hint(ref)).exists()]
        missing_style_refs = [ref for ref in local_styles if not ref.startswith(("http://", "https://")) and not (qodeyard / normalize_file_hint(ref)).exists()]
        if missing_script_refs:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"Missing local HTML references: {', '.join(sorted(set(missing_script_refs)))}",
                "files": ["index.html"],
            })
        if missing_style_refs:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"Missing local stylesheet references: {', '.join(sorted(set(missing_style_refs)))}",
                "files": ["index.html"],
            })
        if js_path.exists() and "app.js" not in local_scripts:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": "index.html does not reference required local script app.js",
                "files": ["index.html", "app.js"],
            })
        if css_path.exists() and "styles.css" not in local_styles:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": "index.html does not reference required local stylesheet styles.css",
                "files": ["index.html", "styles.css"],
            })

    if html and js:
        html_ids = _collect_html_ids(html)
        js_ids = _collect_js_id_refs(js)
        missing_ids = sorted(js_ids - html_ids)
        if missing_ids:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"JavaScript references missing DOM ids: {', '.join(missing_ids)}",
                "files": ["app.js", "index.html"],
            })
        if "addEventListener" not in js:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": "app.js does not register any addEventListener handlers for interactive UI behavior",
                "files": ["app.js"],
            })

    storage_keys = _extract_exact_localstorage_keys(task_text)
    if storage_keys and js:
        used_keys = sorted(_collect_localstorage_keys(js))
        missing_keys = [key for key in storage_keys if key not in used_keys]
        extra_keys = [key for key in used_keys if key not in storage_keys]
        if missing_keys:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"app.js is missing required localStorage keys: {', '.join(missing_keys)}",
                "files": ["app.js"],
            })
        if extra_keys:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"app.js uses undeclared localStorage keys: {', '.join(extra_keys)}",
                "files": ["app.js"],
            })

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if all(day.lower() in task_text.lower() for day in weekdays) and html:
        missing_days = [day for day in weekdays if day not in html and day.lower() not in html.lower()]
        if missing_days:
            issues.append({
                "source": "frontend_contract",
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"Meal-plan day labels missing from HTML: {', '.join(missing_days)}",
                "files": ["index.html"],
            })

    return issues



def _collect_python_symbols(module_text: str) -> set[str]:
    symbols = set()
    for pattern in [r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", r"^def\s+([A-Za-z_][A-Za-z0-9_]*)", r"^([A-Za-z_][A-Za-z0-9_]*)\s*="]:
        symbols.update(re.findall(pattern, module_text or "", flags=re.MULTILINE))
    return symbols



def evaluate_python_fastapi_integration(worqspace_root: Path, scope_files: list[str] | None = None) -> list[dict]:
    qodeyard = worqspace_root / "qodeyard"
    scope_set = set(normalize_file_hints(scope_files)) if scope_files else set()

    python_files = [normalize_file_hint(path.relative_to(qodeyard)) for path in qodeyard.rglob("*.py") if path.is_file()]
    if scope_set:
        python_files = [item for item in python_files if item in scope_set or Path(item).name in {Path(s).name for s in scope_set}]
    if not python_files:
        return []

    module_texts = {rel: _read_text(qodeyard / rel) for rel in python_files}
    symbol_index = {rel: _collect_python_symbols(text) for rel, text in module_texts.items()}
    issues: list[dict] = []

    for rel, text in module_texts.items():
        for match in re.finditer(r"^from\s+([A-Za-z0-9_./]+)\s+import\s+(.+)$", text, flags=re.MULTILINE):
            module_name = match.group(1).replace(".", "/")
            if module_name.startswith("fastapi") or module_name.startswith("pydantic"):
                continue
            import_path = normalize_file_hint(f"{module_name}.py")
            if import_path not in symbol_index:
                continue
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

    if "main.py" in module_texts:
        main_text = module_texts["main.py"]
        route_files = [rel for rel in python_files if rel.endswith("_routes.py") or rel.startswith("routes/")]
        missing_route_refs = []
        for rel in route_files:
            stem = Path(rel).stem.replace("_routes", "")
            if stem and stem not in main_text and Path(rel).stem not in main_text:
                missing_route_refs.append(rel)
        if route_files and "include_router" not in main_text:
            issues.append({
                "source": "python_integration",
                "severity": "error",
                "scope": "python_integration",
                "message": "main.py does not include_router any route modules",
                "files": ["main.py"] + route_files,
            })
        elif missing_route_refs:
            issues.append({
                "source": "python_integration",
                "severity": "error",
                "scope": "python_integration",
                "message": f"main.py appears to omit route-module registration for: {', '.join(sorted(missing_route_refs))}",
                "files": ["main.py"] + sorted(missing_route_refs),
            })

    task_text = _load_task_text(worqspace_root)
    if "storage/uploads" in task_text.lower():
        for rel, text in module_texts.items():
            if rel.endswith("file_routes.py") or "upload" in rel.lower():
                if "storage/uploads" not in text and re.search(r"['\"]uploads['\"]", text):
                    issues.append({
                        "source": "python_integration",
                        "severity": "error",
                        "scope": "python_integration",
                        "message": f"{rel} uses uploads path but not required storage/uploads path",
                        "files": [rel],
                    })

    return issues



def collect_scope_validation_issues(
    worqspace_root: Path,
    *,
    scope_files: list[str] | None = None,
    target_build_groups: list[str] | None = None,
) -> list[dict]:
    del target_build_groups
    issues: list[dict] = []
    issues.extend(evaluate_frontend_group_contracts(worqspace_root, scope_files=scope_files))
    issues.extend(evaluate_python_fastapi_integration(worqspace_root, scope_files=scope_files))
    return issues
