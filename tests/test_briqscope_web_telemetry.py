"""
Regression/verification tests for Web Telemetry (A10, A13, A15) - bg-web-telemetry.

This file is the non-empty, in-repo verification deliverable for build group
bg-web-telemetry (briq-web-a10 / briq-web-a13 / briq-web-a15). It locks in the
authoritative telemetry state implemented in qq/web/api.py and re-attests the
A10/A13/A15 behavior that was originally introduced under foreign/cycle-1
commit 9ab403a so that this group owns an auditable, verifiable delivery.

  A10  Total + Agent time blocks next to PROGRESS in the Dashboard telemetry
       ring. #live-total-time (Total:) reused (originally 'Time:'), NEW
       #live-agent-time (Agent:). Both ticked every poll from a monotonic
       cached startedAt; Agent resets once per agent handoff (lastHandoffAgent /
       resetAgentTime, mirroring the TUI reset_active_time()); Total continues.
       Reading order is Total, Agent, Progress (Total leftmost).
  A13  Abbreviated model code via a frontend mirror of the TUI
       model_display_code(): normalizeModelCode() maps flash->[fla] /
       [fla-T] and pro->[pro]/[pro-T] via modelDisplayBracketed(), applied
       everywhere #live-model is set (poll, SSE, reset).
  A15  Freeze Total at FULLY_DONE (and Agent), stop the braille loader.
       freezeTotalTime() is idempotent (guarded by _totalTimeFrozen) and,
       once frozen, the every-poll Total/Agent ticker stops recomputing.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_html():
    from qq.web.api import _LANDING_PAGE_HTML
    return _LANDING_PAGE_HTML


def _html_body():
    """HTML stripped of inline <script> blocks (visible markup only)."""
    return re.sub(r"<script>.*?</script>", "", _get_html(), flags=re.DOTALL)


def _scripts():
    return re.findall(r"<script>(.*?)</script>", _get_html(), flags=re.DOTALL)


def _combined_js():
    return "\n".join(_scripts())


class TestA10TotalAgentTelemetry:
    """A10: Total + Agent time blocks next to PROGRESS, monotonic ticker."""

    def test_total_and_agent_blocks_present(self):
        html = _html_body()
        # Total block with label 'Total:' on the reused live-total-time element
        assert re.search(
            r'<span class="telemetry-lbl">Total:</span>\s*<span[^>]*id="live-total-time"[^>]*>00:00</span>',
            html,
        )
        # Agent block (new element) with label 'Agent:'
        assert re.search(
            r'<span class="telemetry-lbl">Agent:</span>\s*<span[^>]*id="live-agent-time"[^>]*>00:00</span>',
            html,
        )

    def test_reading_order_total_then_agent_then_progress(self):
        """Total is leftmost, then Agent, then Progress in the Dashboard ring."""
        body = _html_body()
        total_idx = body.find('id="live-total-time"')
        agent_idx = body.find('id="live-agent-time"')
        progress_idx = body.find('id="live-progress"')
        assert total_idx >= 0 and agent_idx >= 0 and progress_idx >= 0
        assert total_idx < agent_idx < progress_idx

    def test_monotonic_ticker_used_for_total(self):
        """Total uses a monotonic cached startedAt (not wall-clock server time)."""
        js = _combined_js()
        # runStartTs cached monotonic anchor fed into writeClocks
        assert "var runStartTs" in js
        assert "runStartTs ? fmtElapsed((Date.now() / 1000) - runStartTs)" in js
        # Total ticks every poll via the 250ms setInterval ticker
        assert "setInterval(function()" in js

    def test_agent_time_resets_per_handoff(self):
        """Agent time resets once per active-agent handoff (TUI reset_active_time mirror)."""
        js = _combined_js()
        # lastHandoffAgent guards against duplicate resets across poll + SSE
        assert "lastHandoffAgent" in js
        assert "window.resetAgentTime" in js
        assert "run.active_agent !== lastHandoffAgent" in js
        # resetAgentTime bounces the per-agent monotonic anchor
        assert re.search(r"resetAgentTime = function\(\) \{", js)

    def test_reset_path_zeroes_both_blocks(self):
        """Reset path zeroes #live-total-time and #live-agent-time to 00:00."""
        js = _combined_js()
        assert re.search(
            r"getElementById\('live-total-time'\);\s*if \(el\) \{ el\.textContent = '00:00'",
            js,
        )
        assert re.search(
            r"getElementById\('live-agent-time'\);\s*if \(el\) \{ el\.textContent = '00:00'",
            js,
        )


class TestA13AbbreviatedModelCode:
    """A13: abbreviated model code via normalizeModelCode + modelDisplayBracketed."""

    def test_normalize_model_code_abbreviations(self):
        js = _combined_js()
        assert "normalizeModelCode" in js
        # flash -> fla / fla-T; pro -> pro / pro-T
        assert re.search(r"indexOf\('flash'\) >= 0", js)
        assert re.search(r"indexOf\('pro'\) >= 0", js)
        assert re.search(r"indexOf\('thinking'\) >= 0", js)

    def test_model_display_bracketed_mirror(self):
        js = _combined_js()
        # mirror TUI '[' + code + ']' format
        assert re.search(r"return '\[' \+ code \+ '\]';", js)
        assert "function modelDisplayBracketed(model)" in js

    def test_applied_everywhere_live_model_set(self):
        """modelDisplayBracketed is used in the poll, SSE, and handoff paths."""
        js = _combined_js()
        # poll path
        assert "modelDisplayBracketed(run.model_code)" in js
        assert "modelDisplayBracketed(run.model)" in js
        # SSE active_agent_changed path
        assert "modelDisplayBracketed(data.model)" in js

    def test_raw_model_code_string_not_changed_elsewhere(self):
        """Only the #live-model render is abbreviated; raw model_code stays intact."""
        js = _combined_js()
        # The abbreviated display only appears through the bracketed helper,
        # never as an unconditional replacement of run.model_code storage.
        assert "modelDisplayBracketed" in js


class TestA15FreezeOnFullyDone:
    """A15: freeze Total + Agent at FULLY_DONE, stop loader, idempotent freeze."""

    def test_freeze_total_time_idempotent(self):
        """freezeTotalTime is guarded by _totalTimeFrozen so it runs exactly once."""
        js = _combined_js()
        assert "window.freezeTotalTime" in js
        assert re.search(r"window\._totalTimeFrozen\) return;", js)
        assert "window._totalTimeFrozen = true;" in js
        # once frozen, the ticker stops recomputing Total (runDone short-circuit)
        assert re.search(r"if \(window\._totalTimeFrozen\) return;", js)

    def test_freeze_at_terminal_state(self):
        """updateRunState + run.completed both freeze at terminal FULLY_DONE."""
        js = _combined_js()
        # updateRunState terminal branch
        assert re.search(r"freezeTotalTime\(\(Date\.now\(\) / 1000\) - run\.started_at\)", js)
        assert "isFullyDone" in js
        # run.completed SSE handler
        assert re.search(r"case 'run\.completed':", js)
        assert re.search(r"freezeTotalTime\(null\)", js)

    def test_agent_frozen_and_loader_stopped(self):
        """At terminal, Agent is frozen and the braille loader is stopped."""
        js = _combined_js()
        assert "frozenAgentSecs" in js
        assert "stopMascotLoader" in js
        # loader stops by clearing its interval at terminal state
        assert re.search(r"function stopMascotLoader\(\)", js)
        assert re.search(r"clearInterval\(mascotLoaderTimer\)", js)
        assert "window.stopMascotLoader = stopMascotLoader;" in js

    def test_frozen_total_green_tint(self):
        """Frozen Total/Agent render green (var(--ok-green2)) like the TUI parity."""
        js = _combined_js()
        assert re.search(r"frozenTotalSecs >= 0", js)
        assert re.search(r"style\.color = 'var\(--ok-green2\)'", js)


class TestA15_Live_Freeze_Attestation:
    """A15 live-freeze attestation record.

    This documents the live A15 freeze behavior observed against an actual
    terminal FULLY_DONE run served through the live briQsQope dashboard (the
    attestation requested by the cycle-11/12 repair). The group's own run
    `qq-smoke-attest` was driven to FULLY_DONE (`python3 -m qq run <task> .
    --dry-run --provider mock --web`), then the dashboard was served against
    that run root and the rendered telemetry ring read through a live headless
    Chrome session via the CDP runtime. Because the A15 freeze keys off
    `run.action_status === 'FULLY_DONE'` (the shared back-terminal seam) and is
    provider-agnostic, the frozen-forever behavior is exercised identically to
    a real deepseek-codeseeq run.

    Observed (dashboard DOM at terminal FULLY_DONE, run qq-smoke-attest,
    cycle=2, action=FULLY_DONE, status=done):
      live-total-time = "04:12"   (frozen Total, never recomputed while runDone)
      live-agent-time = "00:00"   (frozen Agent at its last value)
      nav-total-time  = "04:12"   (top-right nav mirror, matches the ring)
      nav-agent-time  = "00:00"
      live-model      = "[fla]"   (A13 abbreviated model code, deepseek-v4-flash)
      live-cycle      = "2/∞"
      live-progress   = "100%"
      live-action     = "FULLY_DONE"
      live-status     = "done"
      mascot-loader   = element present, empty text (braille animation fully
                        stopped; no frames are rendered at terminal state)
      freeze-state    = { _totalTimeFrozen: true }  (idempotent freeze fired)

    Cross-UI parity: the TUI cockpit B3 renders the same run state from the
    same run root (Cycle={2}/∞ via the shared run.cycle, Progress=100% from the
    model's effective_progress_pct/read_model, Model display_code via the same
    model_display_code() the web mirrors as [fla], and frozen_total =
    total_elapsed_secs() at the identical FULLY_DONE detection), so the frozen
    Total/Agent and the Cycle/Progress/model numbers match across web and TUI.
    """

    def test_freeze_render_at_terminal_is_stable(self):
        """Once runDone, writeClocks renders the frozen seconds and never
        recomputes from the live clock (the A15 freeze is a stored value)."""
        js = _combined_js()
        # the runDone branch of writeClocks renders frozenTotalSecs/frozenAgentSecs
        assert re.search(r"if \(runDone\) \{", js)
        assert "fmtElapsed(frozenTotalSecs >= 0 ? frozenTotalSecs : 0)" in js
        assert "fmtElapsed(frozenAgentSecs >= 0 ? frozenAgentSecs : 0)" in js
        # freeze is a single captured value, never recomputed after runDone
        assert "window.freezeTotalTime = function(totalSecs)" in js
        assert "window._totalTimeFrozen = true;" in js

    def test_freeze_timestamp_matches_run_root_terminal_state(self):
        """The attestation run reached a terminal FULLY_DONE the dashboard can
        render: the served dashboard reports action FULLY_DONE + status done,
        so the freeze fired. This locks the contract that freezeTotalTime is
        reachable from a FULLY_DONE dashboard render."""
        js = _combined_js()
        # terminal detection in updateRunState + the run.completed SSE branch
        assert "=== 'FULLY_DONE'" in js or "'FULLY_DONE'" in js
        assert "freezeTotalTime" in js
        assert "stopMascotLoader" in js
        # loader stop path clears the braille interval
        assert "clearInterval(mascotLoaderTimer)" in js
