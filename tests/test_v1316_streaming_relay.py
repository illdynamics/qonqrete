import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qrane"))

import qrane
from qrane import ConciseStreamRenderer, decode_stream_mode_key_events, extract_stream_payload, iter_ready_lines


def test_iter_ready_lines_relays_partial_output_before_newline(tmp_path):
    script_path = tmp_path / "slow_partial_printer.py"
    script_path.write_text(
        "import sys\n"
        "import time\n"
        "sys.stdout.write('PARTIAL-START')\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.45)\n"
        "sys.stdout.write(' PARTIAL-END\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )

    with subprocess.Popen(
        ["python3", str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    ) as proc:
        reads = [proc.stdout, proc.stderr]
        buffers = {}
        received = []
        received_times = []
        started = time.time()

        while reads:
            for stream, line in iter_ready_lines(proc, reads, buffers):
                if stream is proc.stdout:
                    received.append(line)
                    received_times.append(time.time() - started)

        proc.wait()

    assert received, "Expected at least one streamed stdout fragment."
    # Key regression guard: we must not wait for newline before relaying.
    assert received_times[0] < 0.35, f"First relay was too late: {received_times[0]:.3f}s"
    assert "".join(received) == "PARTIAL-START PARTIAL-END\n"


def test_iter_ready_lines_keeps_line_assembly_stable(tmp_path):
    script_path = tmp_path / "line_assembly_printer.py"
    script_path.write_text(
        "import sys\n"
        "import time\n"
        "sys.stdout.write('Line 1\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.1)\n"
        "sys.stdout.write('Line 2')\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.1)\n"
        "sys.stdout.write(' continued\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )

    with subprocess.Popen(
        ["python3", str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    ) as proc:
        reads = [proc.stdout, proc.stderr]
        buffers = {}
        parts = []
        while reads:
            for stream, line in iter_ready_lines(proc, reads, buffers):
                if stream is proc.stdout:
                    parts.append(line)

        proc.wait()

    assert "".join(parts) == "Line 1\nLine 2 continued\n"


def test_extract_stream_payload_parses_stream_prefix():
    assert extract_stream_payload("[stream:construqtor] ```python:app.py") == "```python:app.py"
    assert extract_stream_payload("plain line") is None


def test_decode_stream_mode_key_events_handles_tab_and_shift_tab():
    events, remainder = decode_stream_mode_key_events(b"\t\x1b[Z")
    assert events == ["tab", "shift_tab"]
    assert remainder == b""

    # Partial Shift+TAB sequence should be retained for next poll.
    events2, remainder2 = decode_stream_mode_key_events(b"\x1b[")
    assert events2 == []
    assert remainder2 == b"\x1b["


def test_concise_stream_renderer_emits_status_and_suppresses_payload():
    renderer = ConciseStreamRenderer()
    assert renderer.feed("### File: `app.py`") == []
    assert renderer.feed("```python:app.py") == ["Writing app.py..."]
    assert renderer.feed("print('hello')") == []
    assert renderer.feed("```") == ["Wrote app.py"]


def test_run_agent_construqtor_stream_mode_inversion_and_hints(monkeypatch, capsys, tmp_path):
    class DummySpinner:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    class DummyStream:
        def fileno(self):
            return 999999

    class DummyPopen:
        def __init__(self, *args, **kwargs):
            self.stdout = DummyStream()
            self.stderr = DummyStream()
            self.returncode = 0
            self._done = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def poll(self):
            return 0 if self._done else None

    class DummyHotkeys:
        def __init__(self):
            self.enabled = True
            self._poll_count = 0

        def start(self):
            pass

        def poll(self):
            self._poll_count += 1
            if self._poll_count == 2:
                return ["tab"]
            if self._poll_count == 3:
                return ["shift_tab"]
            return []

        def stop(self):
            pass

    iter_state = {"calls": 0}

    def fake_iter_ready_lines(proc, reads, _buffers):
        idx = iter_state["calls"]
        iter_state["calls"] += 1
        if idx == 0:
            yield proc.stdout, "[stream:construqtor] raw-default-line-1\n"
            return
        if idx == 1:
            yield proc.stdout, "[stream:construqtor] ```python:app.py\n"
            return
        if idx == 2:
            yield proc.stdout, "[stream:construqtor] raw-after-shift-tab-line-2\n"
            return
        if idx == 3:
            yield proc.stdout, "[stream:construqtor] raw-after-shift-tab-line-3\n"
            return
        reads.clear()
        proc._done = True

    monkeypatch.setattr(qrane, "Spinner", DummySpinner)
    monkeypatch.setattr(qrane, "StreamModeHotkeys", DummyHotkeys)
    monkeypatch.setattr(qrane, "iter_ready_lines", fake_iter_ready_lines)
    monkeypatch.setattr(qrane, "get_worqspace", lambda: tmp_path)
    monkeypatch.setattr(qrane, "get_agent_prefix", lambda name, _color, _prefix: f"[{name}] ")
    monkeypatch.setattr(subprocess, "Popen", DummyPopen)

    result = qrane.run_agent(
        "construqtor",
        ["python3", "fake_worker.py"],
        "uQQ",
        "",
        tmp_path / "qonsole_construqtor.log",
        {},
    )
    assert result is True

    output = capsys.readouterr().out
    assert "Press TAB to view normal coding output" in output
    assert output.count("Press TAB to view normal coding output") == 2
    assert "Normal coding output enabled — press Shift+TAB to return to raw mode" in output
    assert "raw-default-line-1" in output
    assert "Writing app.py..." in output
    assert "raw-after-shift-tab-line-2" in output
    assert "raw-after-shift-tab-line-3" in output


def test_stream_mode_hotkeys_non_tty_safe(monkeypatch):
    class FakeStdin:
        def isatty(self):
            return False

        def fileno(self):
            return 0

    class FakeStdout:
        def isatty(self):
            return False

    monkeypatch.setattr(qrane.sys, "stdin", FakeStdin())
    monkeypatch.setattr(qrane.sys, "stdout", FakeStdout())

    hotkeys = qrane.StreamModeHotkeys()
    assert hotkeys.enabled is False
    hotkeys.start()
    assert hotkeys.poll() == []
    hotkeys.stop()


def test_qrane_source_no_outer_heartbeat_function():
    source = (ROOT / "qrane" / "qrane.py").read_text(encoding="utf-8")
    assert "def heartbeat_message" not in source
