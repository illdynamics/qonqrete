"""
Regression tests for .prompts/tweaks.md — QonQrete briQsQope dashboard upgrades.
Tests: phrase ticker, mascot-card removal, deck resizer/splitter.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── LANDING PAGE TESTS ──
def _get_html():
    from qq.web.api import _LANDING_PAGE_HTML
    return _LANDING_PAGE_HTML


def _get_scripts():
    """Return all inline script blocks."""
    html = _get_html()
    return re.findall(r'<script>(.*?)</script>', html, re.DOTALL)


def _get_combined_js():
    return '\n'.join(_get_scripts())


class TestTickerPresence:
    """Upgrade 1: QonQrete phrase transmission banner."""

    def test_ticker_element_in_nav_spacer(self):
        """The ticker is inside the nav-spacer between SESSIONS and CONNECTED."""
        html = _get_html()
        assert 'qonqrete-transmission' in html
        assert 'transmission-viewport' in html
        assert 'transmission-track' in html
        # Verify it's inside nav-spacer
        nav_spacer_match = re.search(r'<div class="nav-spacer">(.*?)</div>\s*<div class="nav-conn-block"', html, re.DOTALL)
        assert nav_spacer_match is not None, "nav-spacer not found before nav-conn-block"
        spacer_content = nav_spacer_match.group(1)
        assert 'qonqrete-transmission' in spacer_content, "ticker not inside nav-spacer"

    def test_ticker_contains_all_phrases(self):
        """All 20 required phrases are present in the phrase array."""
        js = _get_combined_js()
        required = [
            "Controlling the void since HTTP 404",
            "We don't write apps. We pour them into production",
            "Autonomy mixed fresh",
            "From vague prompt to hardened QonQrete",
            "Release the cybersquid",
            "Blueprints are temporary",
            "Built in the dark",
            "Your requirements entered the yard",
            "Measure twice. Spawn agents",
            "Turning TODO graveyards",
            "No cowboy coding",
            "We monkeypatch reality",
            "Concrete logic. Reinforced prompts",
            "The cybersquid reviewed your architecture",
            "One prompt in. Entire application out",
            "Autonomous by design",
            "Built from tickets",
            "We don't fight technical debt",
            "Constructing tomorrow",
            "Fully done means FULLY_DONE",
        ]
        for phrase in required:
            assert phrase in js, f"Missing phrase: {phrase}"

    def test_single_phrase_array(self):
        """Only one authoritative phrase array definition exists."""
        js = _get_combined_js()
        # Count only the defining assignment, not references
        count = js.count('var QONQRETE_BANNER_PHRASES')
        assert count == 1, f"Expected 1 QONQRETE_BANNER_PHRASES definition, found {count}"

    def test_single_phrase_approach(self):
        """Single phrase element is reused with solo-phrase class for sequential display."""
        js = _get_combined_js()
        assert 'phrase-solo' in js
        assert 'phraseIndex' in js
        assert 'currentItem' in js

    def test_animation_keyframes_present(self):
        """scrollPhraseIn and scrollPhraseOut keyframes are defined."""
        js_or_html = _get_combined_js() + '\n' + _get_html()
        assert 'scrollPhraseIn' in js_or_html
        assert 'scrollPhraseOut' in js_or_html
        assert 'entering' in js_or_html
        assert 'exiting' in js_or_html

    def test_pause_on_hover(self):
        """Pause-on-hover and focus handlers exist."""
        js = _get_combined_js()
        assert "mouseenter" in js or "mouseover" in js
        assert "paused" in js
        assert "focusin" in js or "focusout" in js

    def test_reduced_motion_support(self):
        """prefers-reduced-motion query exists."""
        html = _get_html()
        assert 'prefers-reduced-motion' in html

    def test_connection_block_present(self):
        """The live Act: action bar replaced the legacy CONNECTED indicator (A2)."""
        html = _get_html()
        assert 'nav-action' in html
        assert 'status-dot' not in html
        assert 'conn-text' not in html

    def test_no_marquee_element(self):
        """No deprecated <marquee> element used."""
        html = _get_html()
        assert '<marquee' not in html.lower()

    def test_aria_live_off(self):
        """Ticker has aria-live="off" to prevent assistive tech re-announcement."""
        html = _get_html()
        assert 'aria-live="off"' in html

    def test_navigational_tabs_present(self):
        """All navigation tabs remain in the HTML."""
        html = _get_html()
        for tab in ['Dashboard', 'Agents', 'Tasks', 'Config', 'Sessions']:
            assert tab in html, f"Missing nav tab: {tab}"

    def test_no_external_fonts(self):
        """No Google Fonts or CDN links."""
        html = _get_html()
        assert 'fonts.googleapis.com' not in html
        assert 'fonts.gstatic.com' not in html
        assert 'cdn.jsdelivr.net' not in html

    def test_no_separator_needed(self):
        """Single-phrase mode doesn't need the diamond separator — each phrase scrolls solo."""
        js = _get_combined_js()
        # The sep variable is no longer used; we just verify keyframes are present
        assert 'scrollPhraseIn' in js


class TestMascotCardRemoval:
    """Upgrade 2: Mascot card removal."""

    def test_mascot_card_html_removed(self):
        """The .mascot-card HTML block is completely gone (not in an HTML element)."""
        html = _get_html()
        # Check that there's no mascot-card HTML element
        assert 'class="mascot-card"' not in html

    def test_mascot_card_inline_text_removed(self):
        """The literal inline slogan text is gone from HTML."""
        html = _get_html()
        assert 'CONSTRUCTOR<br>WE BUILD<br>WHAT OTHERS<br>DESIGN' not in html

    def test_slogan_text_removed(self):
        """The 'CONSTRUCTOR / WE BUILD / WHAT OTHERS / DESIGN' text is gone from HTML."""
        html = _get_html()
        # Get the HTML part only (strip script blocks)
        html_body = re.sub(r'<script>.*?</script>', '', html, flags=re.DOTALL)
        assert 'CONSTRUCTOR' not in html_body or 'WE BUILD' not in html_body

    def test_mascot_card_css_removed(self):
        """No CSS rules for .mascot-card remain."""
        html = _get_html()
        styles = re.findall(r'<style>(.*?)</style>', html, re.DOTALL)
        for style_block in styles:
            assert '.mascot-card' not in style_block, "mascot-card CSS still present"

    def test_big_mascot_area_kept(self):
        """.big-mascot-area remains for the large lower-right cybersquid."""
        html = _get_html()
        assert 'big-mascot-area' in html

    def test_system_side_rail_kept(self):
        """The hazard-stripe side rail is removed from the landing page."""
        html = _get_html()
        assert 'system-side-rail' not in html
        assert 'sys-pipe' not in html
        assert 'sys-hazard-strip' not in html
        assert 'sys-status-module' not in html
        assert 'sys-online-text' not in html
        assert 'sys-brand-badge' not in html

    def test_cybersquid_sm_kept_for_empty_bays(self):
        """.cybersquid-sm class still present for empty-bay usage."""
        html = _get_html()
        assert '.cybersquid-sm' in html
        assert 'empty-bay' in html

    def test_event_log_expands_leftward(self):
        """After mascot removal, Event Log is the first child in bottom deck."""
        html = _get_html()
        bottom_deck_match = re.search(
            r'<div class="bottom-instrument-deck">(.*?)</div>\s*<!-- Big cybersquid',
            html, re.DOTALL
        )
        assert bottom_deck_match is not None, "Could not find bottom-instrument-deck"
        deck_content = bottom_deck_match.group(1)
        assert 'event-log-panel' in deck_content
        assert 'mascot-card' not in deck_content


class TestDeckResizer:
    """Upgrade 3: Draggable horizontal divider between workspace and event log."""

    def test_deck_resizer_element_exists(self):
        """The deck-resizer separator exists."""
        html = _get_html()
        assert 'id="deck-resizer"' in html
        assert 'class="deck-resizer"' in html

    def test_resizer_between_workyard_and_deck(self):
        """Resizer sits between workyard-main and bottom-instrument-deck."""
        html = _get_html()
        wy_pos = html.find('class="workyard-main"')
        dr_pos = html.find('id="deck-resizer"')
        bd_pos = html.find('class="bottom-instrument-deck"')
        assert wy_pos > 0 and dr_pos > 0 and bd_pos > 0, "Key elements not found"
        assert wy_pos < dr_pos < bd_pos, "Resizer not between workyard and bottom deck"

    def test_css_custom_property_for_height(self):
        """Bottom deck height uses --bottom-deck-height CSS property."""
        html = _get_html()
        assert '--bottom-deck-height' in html
        assert 'var(--bottom-deck-height)' in html

    def test_resizer_aria_attributes(self):
        """ARIA separator attributes exist."""
        html = _get_html()
        assert 'role="separator"' in html
        assert 'aria-orientation="horizontal"' in html
        assert 'aria-label="Resize ticket board and event log"' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html
        assert 'aria-valuenow' in html

    def test_pointer_events_resize_logic(self):
        """Pointer capture and resize logic exists in JS."""
        js = _get_combined_js()
        assert 'pointerdown' in js
        assert 'pointermove' in js
        assert 'pointerup' in js or 'pointercancel' in js
        assert 'setPointerCapture' in js

    def test_min_max_clamping(self):
        """Min/max clamping exists to prevent unusable panes."""
        js = _get_combined_js()
        assert 'calculateDeckResizeBounds' in js

    def test_localstorage_persistence(self):
        """localStorage persistence with versioned key."""
        js = _get_combined_js()
        assert 'qonqrete.bottomDeckHeight.v1' in js

    def test_keyboard_accessibility(self):
        """Keyboard arrow key handling exists."""
        js = _get_combined_js()
        assert 'ArrowUp' in js
        assert 'ArrowDown' in js

    def test_home_end_keys(self):
        """Home and End keys reset to min/max."""
        js = _get_combined_js()
        assert "'Home'" in js or '"Home"' in js
        assert "'End'" in js or '"End"' in js

    def test_double_click_reset(self):
        """Double-click resets to default 200px."""
        js = _get_combined_js()
        assert 'dblclick' in js

    def test_row_resize_cursor(self):
        """row-resize cursor is used."""
        html = _get_html()
        assert 'row-resize' in html

    def test_workyard_min_height(self):
        """Workyard has min-height to prevent collapsing."""
        html = _get_html()
        assert 'min-height' in html

    def test_drag_body_class(self):
        """deck-resizing body class used during drag."""
        js = _get_combined_js()
        assert 'deck-resizing' in js

    def test_text_selection_disabled_css(self):
        """Text selection disabled during drag via CSS."""
        js_or_css = _get_combined_js() + '\n' + _get_html()
        assert 'user-select' in js_or_css or 'userSelect' in js_or_css


class TestJsSyntax:
    """Ensure combined JS still passes node --check."""

    def test_node_check(self):
        """Extracted JS must pass node --check."""
        import shutil
        if not shutil.which("node"):
            pytest.skip("node not available")
        combined = _get_combined_js()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tf:
            tf.write(combined)
            tf_path = tf.name
        try:
            result = subprocess.run(
                ["node", "--check", tf_path],
                capture_output=True, text=True, timeout=10
            )
            assert result.returncode == 0, f"node --check failed: {result.stderr}"
        finally:
            os.unlink(tf_path)


class TestIntegration:
    """Integration: existing functionality preserved."""

    def test_switch_view_present(self):
        """switchView function still present."""
        js = _get_combined_js()
        assert 'switchView' in js

    def test_update_board_from_model_present(self):
        """updateBoardFromModel function still present."""
        js = _get_combined_js()
        assert 'updateBoardFromModel' in js

    def test_sse_init_present(self):
        """SSE init still present."""
        js = _get_combined_js()
        assert 'initSSE' in js
        assert 'EventSource' in js

    def test_session_selector_intact(self):
        """Session selector functions intact."""
        js = _get_combined_js()
        assert 'openSessionSelector' in js
        assert 'closeSessionSelector' in js
        assert 'refreshSessions' in js

    def test_timer_code_intact(self):
        """Timer code still present."""
        js = _get_combined_js()
        assert 'resetRunTimeForNewRun' in js
        assert 'freezeTotalTime' in js

    def test_cybersquid_renderer_intact(self):
        """Cybersquid renderer still working."""
        js = _get_combined_js()
        assert 'cybersquid-svg' in js or 'renderSquid' in js

    def test_idle_mode_intact(self):
        """Idle mode functions intact."""
        js = _get_combined_js()
        assert 'setIdleState' in js
        assert 'checkIdleMode' in js

    def test_connection_status_intact(self):
        """Action-status functions drive the live Act: bar (A2)."""
        js = _get_combined_js()
        assert 'setActionStatus' in js
        assert 'nav-action' in js
        assert 'setConnectionStatus' not in js
