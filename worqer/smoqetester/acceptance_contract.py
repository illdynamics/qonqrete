"""Acceptance contract extraction from task specs and generation for browser tests.

Produces a machine-readable acceptance contract (JSON/YAML) from task
requirements, driving deterministic checks and Playwright browser tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONTRACT_SCHEMA_VERSION = "acceptance-contract.v1"


def extract_contract_from_task_spec(task_spec: dict) -> dict[str, Any]:
    """Extract an acceptance contract from a task specification dict."""
    contract: dict[str, Any] = {
        "schema_version": DEFAULT_CONTRACT_SCHEMA_VERSION,
        "index_file": task_spec.get("index_file", "index.html"),
    }

    # Required files
    files = task_spec.get("required_files") or []
    if files:
        contract["required_files"] = sorted(set(files))

    # Forbidden extra files
    forbidden = task_spec.get("forbidden_files") or []
    if forbidden:
        contract["forbidden_files"] = sorted(set(forbidden))

    # UI elements
    ui = task_spec.get("required_ui_elements") or task_spec.get("required_selectors") or []
    if ui:
        contract["required_selectors"] = sorted(set(str(s) for s in ui))

    # Interactable
    int_el = task_spec.get("interactable_elements") or task_spec.get("interactable_selectors") or []
    if int_el:
        contract["interactable_selectors"] = sorted(set(str(s) for s in int_el))

    # Storage keys
    ls_keys = task_spec.get("localStorage_keys") or []
    if ls_keys:
        contract["localStorage_keys"] = sorted(set(str(k) for k in ls_keys))
    ss_keys = task_spec.get("sessionStorage_keys") or []
    if ss_keys:
        contract["sessionStorage_keys"] = sorted(set(str(k) for k in ss_keys))

    # User flows
    flows = task_spec.get("user_flows") or task_spec.get("required_user_flows") or []
    if flows:
        contract["user_flows"] = flows

    # Reload persistence
    if task_spec.get("check_reload_persistence") or task_spec.get("requires_persistence"):
        contract["check_reload_persistence"] = True

    # Network isolation
    if task_spec.get("no_external_network") or task_spec.get("offline_only"):
        contract["no_external_network"] = True

    # Validation messages
    val_msgs = task_spec.get("required_validation_messages") or []
    if val_msgs:
        contract["forbidden_texts"] = []  # placeholder; actual forbidden texts are inverted
        contract["expected_validation_messages"] = sorted(set(str(m) for m in val_msgs))

    # Scope constraints
    scope = task_spec.get("scope_constraints") or task_spec.get("constraints") or {}
    if scope:
        contract["scope_constraints"] = scope

    # Forbidden text
    forbid_text = task_spec.get("forbidden_texts") or task_spec.get("forbidden_placeholders") or []
    if forbid_text:
        contract["forbidden_texts"] = sorted(set(str(t) for t in forbid_text))

    # Responsive viewports
    vp = task_spec.get("responsive_viewports") or []
    if vp:
        contract["responsive_viewports"] = vp

    return contract


def make_recipe_planner_contract() -> dict[str, Any]:
    """Generate the canonical acceptance contract for the recipe planner benchmark."""
    return {
        "schema_version": DEFAULT_CONTRACT_SCHEMA_VERSION,
        "index_file": "index.html",
        "required_files": ["index.html", "styles.css", "script.js"],
        "forbidden_files": [],
        "required_selectors": [
            "#recipe-form",
            "#recipe-list",
            "#search-input",
            "#category-filter",
            "#favorites-only-btn",
            "#weekly-plan",
            "#stats-panel",
        ],
        "interactable_selectors": [
            "#recipe-form input[name='recipe-name']",
            "#recipe-form textarea[name='ingredients']",
            "#recipe-form textarea[name='steps']",
            "#recipe-form select[name='category']",
            "#recipe-form button[type='submit']",
            "#search-input",
            "#category-filter",
            "#favorites-only-btn",
        ],
        "localStorage_keys": ["qonqrete_recipes"],
        "sessionStorage_keys": [],
        "check_reload_persistence": True,
        "no_external_network": True,
        "forbidden_texts": [
            "TODO", "FIXME", "lorem ipsum", "placeholder",
            "scaffold", "template content",
        ],
        "user_flows": [
            {
                "name": "add_recipe",
                "steps": [
                    {"action": "fill", "selector": "#recipe-form input[name='recipe-name']", "value": "Pasta"},
                    {"action": "fill", "selector": "#recipe-form textarea[name='ingredients']", "value": "pasta, tomato"},
                    {"action": "fill", "selector": "#recipe-form textarea[name='steps']", "value": "Boil, simmer"},
                    {"action": "select", "selector": "#recipe-form select[name='category']", "value": "Dinner"},
                    {"action": "click", "selector": "#recipe-form button[type='submit']"},
                    {"action": "wait", "ms": 500},
                ],
                "expect_text": "Pasta",
            },
            {
                "name": "search_by_name",
                "steps": [
                    {"action": "fill", "selector": "#search-input", "value": "Pasta"},
                    {"action": "wait", "ms": 300},
                ],
                "expect_text": "Pasta",
            },
            {
                "name": "add_favorite",
                "steps": [
                    {"action": "click", "selector": ".favorite-btn"},
                    {"action": "wait", "ms": 300},
                ],
            },
            {
                "name": "favorites_filter",
                "steps": [
                    {"action": "click", "selector": "#favorites-only-btn"},
                    {"action": "wait", "ms": 300},
                ],
            },
        ],
        "responsive_viewports": [
            {"width": 375, "height": 812},
            {"width": 1024, "height": 768},
        ],
    }


def write_contract(contract: dict, path: Path) -> Path:
    """Write acceptance contract to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".yaml":
        import yaml
        path.write_text(yaml.dump(contract, default_flow_style=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return path


__all__ = [
    "DEFAULT_CONTRACT_SCHEMA_VERSION",
    "extract_contract_from_task_spec",
    "make_recipe_planner_contract",
    "write_contract",
]
