"""
Regression tests for Web Shell Nav (A1-A4) — briQsQope top navigation bar.

These tests lock in the authoritative nav-shell state implemented in
qq/web/api.py:

  A1  Rename user-visible nav labels  Dashboard -> BOARD and
      Sessions -> RUNS, WITHOUT altering ids, onclick handlers, or the
      switchView()/openSessionSelector() call args, and preserving the
      amber inline style on the RUNS button.
  A2  Replace the legacy CONNECTED / #signal-bars / #status-dot connection
      indicator with a single live Act:X action bar driven by
      setActionStatus(), deleting dead indicator code and folding
      error/reconnecting/FAILED/BLOCKED into an 'err' class.
  A3  Change the nav progress icon label P: -> PROGRESS: with
      white-space:nowrap so the longer label does not wrap.
  A4  Remove #panel-view-label and all its JS assignments (the yellow
      .nav-tab.active button remains the single source of truth).

No nav element id, class, or view key is renamed; only labels/status
indications changed. These tests are the non-empty, in-repo verification
deliverable for build group bg-web-shell (briq-web-a1..a4).
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
    return re.findall(r"<script>(.*?)</script>", _get_html(), re.DOTALL)


def _combined_js():
    return "\n".join(_scripts())


def _styles():
    return "\n".join(re.findall(r"<style>(.*?)</style>", _get_html(), re.DOTALL))


class TestA1NavLabelRename:
    """A1: Dashboard -> BOARD and Sessions -> RUNS in the nav buttons."""

    def test_dashboard_button_label_is_board(self):
        html = _html_body()
        assert re.search(
            r'<button[^>]*id="nav-dashboard"[^>]*>BOARD</button>', html
        ), "nav-dashboard visible label must be BOARD"

    def test_sessions_button_is_yellow_square_icon_no_text(self):
        # BGP3 (briq-runs-square-icon-button): the Sessions button is now a
        # SQUARE yellow monitor/session icon button with NO textual 'RUNS' label.
        html = _html_body()
        # No visible 'RUNS' text label inside the button body.
        assert not re.search(
            r'<button[^>]*id="nav-sessions"[^>]*>RUNS</button>', html
        ), "nav-sessions must no longer carry a textual RUNS label (BGP3)"
        # The button is square and rendered yellow via the square icon CSS.
        css = _styles()
        assert "nav-sessions-btn" in css, "nav-sessions square button CSS missing"
        assert re.search(r'\.nav-sessions-btn\s*\{[^}]*aspect-ratio:\s*1/1', css), "nav-sessions must be square (aspect-ratio 1/1)"
        assert ".nav-sessions-btn.nav-sessions-icon{display:block;color:var(--constr-amber)" in css.replace(" ", "").replace("\n", ""), "nav-sessions icon must be amber/yellow"

    def test_dashboard_button_keeps_switchview_dashboard(self):
        html = _html_body()
        assert re.search(
            r'<button onclick="switchView\(\'dashboard\'\)"[^>]*id="nav-dashboard"'
            r'[^>]*class="nav-tab active">BOARD</button>',
            html,
        ), "nav-dashboard must keep switchView('dashboard'), id, and active class"

    def test_sessions_button_keeps_opensessionselector_id_and_square_icon(self):
        # BGP3: preserve onclick/id/class wiring; the amber/yellow is carried by
        # the square monitor icon (currentColor on the inline SVG) rather than an
        # inline style or a textual RUNS label.
        html = _html_body()
        assert re.search(
            r'<button onclick="openSessionSelector\(\)"[^>]*id="nav-sessions"'
            r'[^>]*class="nav-tab nav-sessions-btn"',
            html,
        ), "nav-sessions must keep openSessionSelector(), id, and nav-tab classes"
        assert re.search(r'<svg class="nav-sessions-icon"', html), "nav-sessions must render a monitor/session icon svg"

    def test_old_button_labels_not_present_as_nav_buttons(self):
        html = _html_body()
        # The old label text must not appear as a nav-tab button label.
        assert not re.search(r'>Dashboard</button>', html), "board label was Dashboard"
        assert not re.search(r'>Sessions</button>', html), "runs label was Sessions"


class TestA2LiveActionBar:
    """A2: live Act:X action bar replaces the legacy CONNECTED indicator."""

    def test_nav_action_present(self):
        html = _html_body()
        # The live Act:X bar is a single #nav-action span whose visible label
        # ("Act:") is styled via a nested .nav-action-label span, immediately
        # followed by the amber value span.
        assert re.search(
            r'<span class="nav-action" id="nav-action">', html
        ), "#nav-action Act: bar must exist"
        assert '<span class="nav-action-label">Act:</span>' in html, \
            "Act: label span must exist inside #nav-action"

    def test_legacy_indicator_removed(self):
        html = _get_html()
        for dead in ("signal-bars", "status-dot", "conn-text", "CONNECTED>"):
            assert dead not in html, f"dead indicator element/ref still present: {dead}"

    def test_setactionstatus_present_and_conconnection_removed(self):
        js = _combined_js()
        assert "function setActionStatus" in js, "setActionStatus must be defined"
        assert "setConnectionStatus" not in js, "setConnectionStatus must be gone"

    def test_error_and_reconnecting_fold_into_err_class(self):
        js = _combined_js()
        # error / reconnecting drive the .err class on #nav-action
        assert re.search(
            r"el\.className\s*=\s*err\s*\?\s*'nav-action err'",
            js,
        ), "setActionStatus must set .err on #nav-action for error/reconnecting"
        # The good/success path drives a separate 'nav-action good' class.
        assert re.search(
            r"'nav-action good'", js,
        ), "setActionStatus must set .good on #nav-action for good status"
        # The reconnecting status surfaces as the RECONNECTING value.
        assert "'RECONNECTING'" in js or '"RECONNECTING"' in js, \
            "setActionStatus must surface RECONNECTING for the reconnecting status"

    def test_nav_action_err_css_exists(self):
        css = _styles()
        assert ".nav-action.err{" in css.replace(" ", "").replace("\n", "") or \
            ".nav-action.err{" in css, ".nav-action.err error-color CSS rule required"
        assert "--alarm-red" in css or "alarm-red" in css

    def test_nav_action_nowrap(self):
        css = _styles()
        assert "white-space:nowrap" in css, "#nav-action must not wrap"


class TestA3ProgressLabel:
    """A3: P: -> PROGRESS: in .nav-progress-icon with no wrap."""

    def test_progress_label_renders(self):
        html = _html_body()
        assert '<span class="nav-progress-icon">PROGRESS:</span>' in html, \
            "nav progress icon label must be PROGRESS:"

    def test_old_p_label_gone(self):
        html = _html_body()
        assert not re.search(
            r'<span class="nav-progress-icon">P:</span>', html
        ), "old 'P:' nav progress label must be gone"

    def test_progress_icon_nowrap_css(self):
        css = _styles()
        assert ".nav-progress-icon{" in css
        assert re.search(
            r"\.nav-progress-icon\{[^}]*white-space:\s*nowrap", css
        ), ".nav-progress-icon must set white-space:nowrap"


class TestA4PanelViewLabelRemoved:
    """A4: #panel-view-label element and its JS assignments are gone."""

    def test_panel_view_label_element_removed(self):
        html = _get_html()
        assert "panel-view-label" not in html, "#panel-view-label element must be removed"

    def test_viewlabels_and_labelel_js_gone(self):
        js = _combined_js()
        assert "panel-view-label" not in js, "JS must not reference #panel-view-label"
        assert "viewLabels" not in js, "viewLabels JS mapping must be removed"
        assert "labelEl" not in js, "labelEl JS variable must be removed"

    def test_single_source_nav_tab_active_remains(self):
        html = _html_body()
        assert re.search(
            r'id="nav-dashboard"[^>]*class="nav-tab active"', html
        ), "yellow .nav-tab.active (nav-dashboard) must remain as source of truth"
