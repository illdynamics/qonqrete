"""Playwright browser smoke-test adapter for frontend deliverables.

Optional capability: skipped gracefully when playwright is not installed.
When enabled, serves static qodeyard files via a local HTTP server (no external
network) and runs browser-based checks driven by an acceptance contract.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from ..base import (
    Adapter,
    SmoketestContext,
    SmoketestResult,
    rel_name,
    result_error,
    result_fail,
    result_pass,
    result_skip,
)
from ..models import (
    EXECUTION_KIND_BROWSER,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
)


def _find_playwright() -> Optional[str]:
    """Locate the playwright CLI binary if installed."""
    for candidate in ("playwright", "npx playwright", "python3 -m playwright"):
        parts = candidate.split()
        if shutil.which(parts[0]):
            return candidate
    return None


def _acceptance_contract_path(qodeyard_path: Path) -> Optional[Path]:
    """Look for an acceptance contract in qodeyard or the parent qage root."""
    candidates = [
        qodeyard_path / "acceptance-contract.json",
        qodeyard_path / "acceptance-contract.yaml",
        qodeyard_path.parent / "acceptance-contract.json",
        qodeyard_path.parent / "acceptance-contract.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _load_acceptance_contract(contract_path: Path) -> dict[str, Any]:
    """Load acceptance contract from JSON or YAML."""
    raw = contract_path.read_text(encoding="utf-8")
    if contract_path.suffix == ".yaml":
        import yaml as _yaml
        return _yaml.safe_load(raw) or {}
    return json.loads(raw)


def _start_static_server(qodeyard_path: Path, port: int = 0) -> tuple[subprocess.Popen, int]:
    """Start a minimal Python HTTP server serving qodeyard, port 0 = auto-assign."""
    import http.server
    import socket
    import threading

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(qodeyard_path), **kwargs)

        def log_message(self, format, *args):
            pass  # silent

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    assigned_port = sock.getsockname()[1]
    sock.close()

    server = http.server.HTTPServer(("127.0.0.1", assigned_port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, assigned_port


def _write_browser_test_script(contract: dict, base_url: str, output_path: Path) -> str:
    """Generate a Playwright test script from the acceptance contract."""
    tests_json = json.dumps(contract, indent=2)

    script = f'''// Auto-generated browser smoke test — do not edit manually.
const {{ chromium }} = require("playwright");
const contract = {tests_json};

function isPresent(value) {{
    return value !== undefined && value !== null;
}}

async function run() {{
    const browser = await chromium.launch({{ headless: true }});
    const context = await browser.newContext({{
        ignoreHTTPSErrors: true,
        bypassCSP: false,  // Honor CSP — do not weaken security
    }});
    const page = await context.newPage();

    const results = [];
    const consoleLogs = [];
    const pageErrors = [];
    const failedRequests = [];

    page.on("console", msg => consoleLogs.push({{ type: msg.type(), text: msg.text() }}));
    page.on("pageerror", err => pageErrors.push(err.message));
    page.on("requestfailed", req => failedRequests.push(req.url()));

    const baseUrl = "{base_url}";

    try {{
        // ─── 1. Page load ──────────────────────────────────────────
        const indexFile = contract.index_file || "index.html";
        const loadUrl = baseUrl + "/" + indexFile;
        const response = await page.goto(loadUrl, {{ waitUntil: "networkidle", timeout: 15000 }});

        if (!response || !response.ok()) {{
            results.push({{ check: "page_load", status: "FAIL", message: `HTTP ${{response ? response.status() : "no response"}}` }});
        }} else {{
            results.push({{ check: "page_load", status: "PASS", message: `Loaded ${{loadUrl}} (HTTP ${{response.status()}})` }});
        }}

        // ─── 2. Console errors ─────────────────────────────────────
        const consoleErrors = consoleLogs.filter(l => l.type === "error");
        if (consoleErrors.length > 0) {{
            results.push({{ check: "console_errors", status: "FAIL", message: `${{consoleErrors.length}} console error(s): ${{JSON.stringify(consoleErrors.slice(0, 5))}}` }});
        }} else {{
            results.push({{ check: "console_errors", status: "PASS", message: "No console errors" }});
        }}

        // ─── 3. Uncaught exceptions ────────────────────────────────
        if (pageErrors.length > 0) {{
            results.push({{ check: "uncaught_exceptions", status: "FAIL", message: `${{pageErrors.length}} uncaught: ${{pageErrors.slice(0, 3).join("; ")}}` }});
        }} else {{
            results.push({{ check: "uncaught_exceptions", status: "PASS", message: "No uncaught exceptions" }});
        }}

        // ─── 4. Failed local asset requests ────────────────────────
        const localFails = failedRequests.filter(u => !u.startsWith("http://") && !u.startsWith("https://") || u.startsWith(baseUrl));
        if (localFails.length > 0) {{
            results.push({{ check: "failed_requests", status: "FAIL", message: `${{localFails.length}} failed request(s): ${{localFails.slice(0, 5).join(", ")}}` }});
        }} else if (failedRequests.length > 0) {{
            results.push({{ check: "failed_requests", status: "WARN", message: `${{failedRequests.length}} external failed request(s); external network may be needed` }});
        }} else {{
            results.push({{ check: "failed_requests", status: "PASS", message: "No failed requests" }});
        }}

        // ─── 5. Required selectors ──────────────────────────────────
        const requiredSelectors = contract.required_selectors || [];
        for (const sel of requiredSelectors) {{
            try {{
                const el = await page.waitForSelector(sel, {{ timeout: 5000 }});
                if (el) {{
                    results.push({{ check: `selector:${{sel}}`, status: "PASS", message: `Selector "${{sel}}" found` }});
                }}
            }} catch (e) {{
                results.push({{ check: `selector:${{sel}}`, status: "FAIL", message: `Required selector "${{sel}}" not found` }});
            }}
        }}

        // ─── 6. Interactable elements ───────────────────────────────
        const interactableSelectors = contract.interactable_selectors || [];
        for (const sel of interactableSelectors) {{
            try {{
                const el = await page.$(sel);
                if (!el) {{
                    results.push({{ check: `interactable:${{sel}}`, status: "FAIL", message: `"${{sel}}" not found` }});
                    continue;
                }}
                const isVisible = await el.isVisible();
                const isEnabled = await el.isEnabled();
                if (isVisible && isEnabled) {{
                    results.push({{ check: `interactable:${{sel}}`, status: "PASS", message: `"${{sel}}" visible and enabled` }});
                }} else {{
                    results.push({{ check: `interactable:${{sel}}`, status: "FAIL", message: `"${{sel}}" visible=${{isVisible}} enabled=${{isEnabled}}` }});
                }}
            }} catch (e) {{
                results.push({{ check: `interactable:${{sel}}`, status: "FAIL", message: `"${{sel}}" error: ${{e.message}}` }});
            }}
        }}

        // ─── 7. localStorage/sessionStorage keys ────────────────────
        const expectedLocalKeys = contract.localStorage_keys || [];
        const actualLocalKeys = await page.evaluate(() => Object.keys(localStorage));
        for (const key of expectedLocalKeys) {{
            if (actualLocalKeys.includes(key)) {{
                results.push({{ check: `localStorage:${{key}}`, status: "PASS", message: `localStorage key "${{key}}" exists` }});
            }} else {{
                results.push({{ check: `localStorage:${{key}}`, status: "FAIL", message: `localStorage key "${{key}}" missing. Present: ${{JSON.stringify(actualLocalKeys)}}` }});
            }}
        }}

        const expectedSessionKeys = contract.sessionStorage_keys || [];
        const actualSessionKeys = await page.evaluate(() => Object.keys(sessionStorage));
        for (const key of expectedSessionKeys) {{
            if (actualSessionKeys.includes(key)) {{
                results.push({{ check: `sessionStorage:${{key}}`, status: "PASS", message: `sessionStorage key "${{key}}" exists` }});
            }} else {{
                results.push({{ check: `sessionStorage:${{key}}`, status: "FAIL", message: `sessionStorage key "${{key}}" missing` }});
            }}
        }}

        // ─── 8. User flows ─────────────────────────────────────────
        const flows = contract.user_flows || [];
        for (const flow of flows) {{
            const flowName = flow.name || "unnamed_flow";
            try {{
                for (const step of (flow.steps || [])) {{
                    if (step.action === "click") {{
                        await page.click(step.selector, {{ timeout: 5000 }});
                    }} else if (step.action === "fill") {{
                        await page.fill(step.selector, step.value || "");
                    }} else if (step.action === "select") {{
                        await page.selectOption(step.selector, step.value || "");
                    }} else if (step.action === "wait") {{
                        await page.waitForTimeout(step.ms || 1000);
                    }}
                    if (step.wait_after_ms) {{
                        await page.waitForTimeout(step.wait_after_ms);
                    }}
                }}
                // Verify expected text after flow
                if (flow.expect_text) {{
                    const bodyText = await page.textContent("body");
                    if (bodyText && bodyText.includes(flow.expect_text)) {{
                        results.push({{ check: `flow:${{flowName}}`, status: "PASS", message: `Text "${{flow.expect_text}}" found` }});
                    }} else {{
                        results.push({{ check: `flow:${{flowName}}`, status: "FAIL", message: `Expected text "${{flow.expect_text}}" not found` }});
                    }}
                }} else {{
                    results.push({{ check: `flow:${{flowName}}`, status: "PASS", message: `Flow completed` }});
                }}
            }} catch (e) {{
                results.push({{ check: `flow:${{flowName}}`, status: "FAIL", message: `Flow error: ${{e.message}}` }});
            }}
        }}

        // ─── 9. Forbidden text/placeholders ─────────────────────────
        const forbiddenTexts = contract.forbidden_texts || [];
        const bodyText = await page.textContent("body");
        if (bodyText) {{
            for (const ft of forbiddenTexts) {{
                if (bodyText.toLowerCase().includes(ft.toLowerCase())) {{
                    results.push({{ check: `forbidden_text:${{ft}}`, status: "FAIL", message: `Forbidden text "${{ft}}" found` }});
                }} else {{
                    results.push({{ check: `forbidden_text:${{ft}}`, status: "PASS", message: `Forbidden text "${{ft}}" absent` }});
                }}
            }}
        }}

        // ─── 10. Network isolation ──────────────────────────────────
        const allRequests: string[] = [];
        page.on("request", req => allRequests.push(req.url()));
        if (contract.no_external_network) {{
            const externalReqs = allRequests.filter(u => !u.startsWith(baseUrl) && !u.startsWith("data:") && !u.startsWith("blob:"));
            if (externalReqs.length > 0) {{
                results.push({{ check: "network_isolation", status: "FAIL", message: `${{externalReqs.length}} unexpected external request(s): ${{externalReqs.slice(0, 5).join(", ")}}` }});
            }} else {{
                results.push({{ check: "network_isolation", status: "PASS", message: "No external network requests" }});
            }}
        }}

        // ─── 11. Reload persistence ─────────────────────────────────
        if (contract.check_reload_persistence) {{
            const preReloadKeys = await page.evaluate(() => Object.keys(localStorage));
            await page.reload({{ waitUntil: "networkidle", timeout: 10000 }});
            const postReloadKeys = await page.evaluate(() => Object.keys(localStorage));
            const missing = preReloadKeys.filter(k => !postReloadKeys.includes(k));
            if (missing.length > 0) {{
                results.push({{ check: "reload_persistence", status: "FAIL", message: `Lost keys after reload: ${{JSON.stringify(missing)}}` }});
            }} else {{
                results.push({{ check: "reload_persistence", status: "PASS", message: `All ${{preReloadKeys.length}} localStorage keys survived reload` }});
            }}
        }}

        // ─── 12. Responsive layout smoke ────────────────────────────
        if (contract.responsive_viewports) {{
            for (const vp of contract.responsive_viewports) {{
                await page.setViewportSize({{ width: vp.width || 375, height: vp.height || 812 }});
                await page.waitForTimeout(500);
                const vpLabel = `${{vp.width || 375}}x${{vp.height || 812}}`;
                try {{
                    const hasOverflow = await page.evaluate(() => {{
                        const html = document.documentElement;
                        return html.scrollWidth > html.clientWidth || html.scrollHeight > html.clientHeight;
                    }});
                    if (hasOverflow) {{
                        results.push({{ check: `responsive:${{vpLabel}}`, status: "WARN", message: `Viewport ${{vpLabel}} has overflow; check layout` }});
                    }} else {{
                        results.push({{ check: `responsive:${{vpLabel}}`, status: "PASS", message: `Viewport ${{vpLabel}} fits without overflow` }});
                    }}
                }} catch (e) {{
                    results.push({{ check: `responsive:${{vpLabel}}`, status: "FAIL", message: `Viewport check error: ${{e.message}}` }});
                }}
            }}
        }}

    }} catch (e) {{
        results.push({{ check: "fatal", status: "FAIL", message: `Browser test crashed: ${{e.message}}` }});
    }} finally {{
        await browser.close();
    }}

    // ─── Output ─────────────────────────────────────────────────
    process.stdout.write(JSON.stringify({{
        results: results,
        console_logs: consoleLogs.slice(0, 50),
        page_errors: pageErrors.slice(0, 10),
        failed_requests: failedRequests.slice(0, 20),
    }}, null, 2));
}}

run().catch(err => {{
    process.stderr.write("FATAL: " + err.message + "\\n");
    process.exit(1);
}});
'''
    output_path.write_text(script, encoding="utf-8")
    return script


def _run_playwright_test(
    qodeyard_path: Path,
    contract: dict,
    ctx: SmoketestContext,
) -> SmoketestResult:
    """Execute a Playwright browser test against qodeyard content."""
    server, port = _start_static_server(qodeyard_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        with tempfile.TemporaryDirectory(prefix="pw_smoke_") as tmpdir:
            tmp = Path(tmpdir)
            script_path = tmp / "smoke_test.js"
            _write_browser_test_script(contract, base_url, script_path)

            pw_cmd = _find_playwright()
            if pw_cmd is None:
                return result_skip(
                    "playwright_browser", "browser_smoke",
                    "Playwright not installed. Install with: npm i playwright  or  pip install playwright && python3 -m playwright install chromium",
                    execution_kind=EXECUTION_KIND_BROWSER,
                    scope="browser_e2e",
                )

            cmd_parts = pw_cmd.split() + [str(script_path)]
            # Try npx-style first, then direct
            result = subprocess.run(
                cmd_parts,
                capture_output=True, text=True, timeout=max(15, ctx.timeout_seconds),
                cwd=str(tmp),
            )

            if result.returncode != 0:
                stderr = (result.stderr or "")[:2000]
                stdout = (result.stdout or "")[:2000]
                # Try to parse partial JSON from stdout
                partial: dict = {}
                try:
                    partial = json.loads(stdout) if stdout.strip().startswith("{") else {}
                except Exception:
                    pass
                return SmoketestResult(
                    adapter="playwright_browser",
                    name="browser_smoke",
                    status=STATUS_FAIL,
                    executed=True,
                    execution_kind=EXECUTION_KIND_BROWSER,
                    message=f"Playwright test failed (exit {result.returncode})",
                    severity=SEVERITY_ERROR,
                    stdout=stdout,
                    stderr=stderr,
                    scope="browser_e2e",
                )

            data = json.loads(result.stdout)
            all_results = data.get("results", [])
            failures = [r for r in all_results if r.get("status") in ("FAIL", "ERROR")]
            warnings_list = [r for r in all_results if r.get("status") == "WARN"]

            failure_detail = "; ".join(
                f"{r['check']}: {r['message']}" for r in failures[:8]
            )

            if failures:
                return SmoketestResult(
                    adapter="playwright_browser",
                    name="browser_smoke",
                    status=STATUS_FAIL,
                    executed=True,
                    execution_kind=EXECUTION_KIND_BROWSER,
                    message=f"Browser checks: {len(all_results)} total, {len(failures)} failed: {failure_detail}",
                    severity=SEVERITY_ERROR,
                    stdout=json.dumps(data, indent=2),
                    scope="browser_e2e",
                )
            elif warnings_list:
                return SmoketestResult(
                    adapter="playwright_browser",
                    name="browser_smoke",
                    status=STATUS_PASS,
                    executed=True,
                    execution_kind=EXECUTION_KIND_BROWSER,
                    message=f"Browser checks: {len(all_results)} passed, {len(warnings_list)} warnings",
                    severity=SEVERITY_WARNING,
                    stdout=json.dumps(data, indent=2),
                    scope="browser_e2e",
                )
            else:
                return SmoketestResult(
                    adapter="playwright_browser",
                    name="browser_smoke",
                    status=STATUS_PASS,
                    executed=True,
                    execution_kind=EXECUTION_KIND_BROWSER,
                    message=f"Browser checks: {len(all_results)} passed",
                    severity=SEVERITY_INFO,
                    stdout=json.dumps(data, indent=2),
                    scope="browser_e2e",
                )

    except subprocess.TimeoutExpired:
        return SmoketestResult(
            adapter="playwright_browser",
            name="browser_smoke",
            status=STATUS_ERROR,
            executed=True,
            execution_kind=EXECUTION_KIND_BROWSER,
            message=f"Browser test timed out after {ctx.timeout_seconds}s",
            severity=SEVERITY_ERROR,
            scope="browser_e2e",
        )
    except Exception as exc:
        return SmoketestResult(
            adapter="playwright_browser",
            name="browser_smoke",
            status=STATUS_ERROR,
            executed=False,
            execution_kind=EXECUTION_KIND_BROWSER,
            message=f"Browser test infrastructure error: {exc}",
            severity=SEVERITY_ERROR,
            scope="browser_e2e",
        )
    finally:
        server.shutdown()


class PlaywrightBrowserAdapter(Adapter):
    """Playwright-based browser smoke testing adapter.

    Optional: gracefully degrades when playwright is not installed.
    Reads acceptance-contract.json from qodeyard to drive checks.
    """

    name = "playwright_browser"
    extensions = (".html", ".htm", ".js", ".mjs")

    def preflight(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        results: list[SmoketestResult] = []
        contract_path = _acceptance_contract_path(ctx.qodeyard_path)
        if contract_path is None:
            results.append(result_skip(
                "playwright_browser", "preflight",
                "No acceptance contract found; browser smoke tests skipped",
                execution_kind=EXECUTION_KIND_BROWSER,
                scope="browser_e2e",
            ))
            return results

        pw = _find_playwright()
        if pw is None:
            results.append(result_skip(
                "playwright_browser", "preflight",
                "Playwright not installed. Install: pip install playwright && python3 -m playwright install chromium",
                execution_kind=EXECUTION_KIND_BROWSER,
                scope="browser_e2e",
            ))
            return results

        results.append(result_pass(
            "playwright_browser", "preflight",
            f"Playwright available: {pw}",
            execution_kind=EXECUTION_KIND_BROWSER,
            scope="browser_e2e",
        ))
        return results

    def project_smoketest(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        contract_path = _acceptance_contract_path(ctx.qodeyard_path)
        if contract_path is None:
            return [result_skip(
                "playwright_browser", "browser_smoke",
                "No acceptance contract found; browser smoke test skipped",
                execution_kind=EXECUTION_KIND_BROWSER,
                scope="browser_e2e",
            )]

        pw = _find_playwright()
        if pw is None:
            return [result_skip(
                "playwright_browser", "browser_smoke",
                "Playwright not installed",
                execution_kind=EXECUTION_KIND_BROWSER,
                scope="browser_e2e",
            )]

        contract = _load_acceptance_contract(contract_path)
        return [_run_playwright_test(ctx.qodeyard_path, contract, ctx)]


__all__ = ["PlaywrightBrowserAdapter"]
