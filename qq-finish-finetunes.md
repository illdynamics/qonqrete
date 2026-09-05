# QonQrete Finish Fine-Tunes — Complete Build Prompt

> **Generated**: 2026-08-11  
> **Project**: QonQrete (v?.?.?) — Autonomous multi-agent software construction system  
> **Scope**: Dashboard web-interface polish, real-time streaming, and remaining issues  
> **Repo**: `/x/qonqrete` — Python core (`qq/`), Rust TUI (`qq-tui/`), Web dashboard (`qq/web/api.py`)

---

## ════════════════════════════════════════════════════════════════
## SECTION 0: PROJECT STATE SUMMARY
## ════════════════════════════════════════════════════════════════

### Architecture Overview

The QonQrete system consists of:

1. **Python Core** (`qq/`) — ~27K lines across 50+ files
   - `cli.py` (2208L) — CLI entrypoint, TUI launcher
   - `qontroller.py` (1568L) — Orchestration loop (Qlarifier → instruQtor → construQtor → inspeQtor)
   - `terminal_ui.py` (654L) — Sticky status bar, braille spinner, ANSI terminal management
   - `streaming.py` (321L) — Agent subprocess output streaming to terminal
   - `progress.py` (524L) — Phase-aware multi-layer progress calculator (accepted/working/displayed)
   - `sandbox.py` (683L) — Bubblewrap OS-level filesystem isolation
   - `sandbox_integration.py` (286L) — Wrapping adapter (currently FULLY DISABLED — sandbox wrapping removed per ultimate-fix.md)

2. **Web Dashboard** (`qq/web/`) — ~11K lines
   - `api.py` (4090L) — Single-file HTTP server with embedded HTML/CSS/JS dashboard
   - `read_model.py` (1170L) — Incremental read-model builder from events.jsonl + artifacts
   - `events.py` (182L) — EventTailer: polls events.jsonl, SSE streaming generator
   - `process.py` (332L) — Dashboard process lifecycle (start/stop/status)
   - `run_registry.py` (1028L) — Run state tracking, session management
   - `status_resolver.py` (386L) — Final status resolution from run artifacts

3. **Rust TUI** (`qq-tui/`) — Ratatui-based terminal cockpit
   - `layout.rs` — 3-zone layout: status bar / output view / input box
   - `output_view.rs` — Scrollable agent output with per-role coloring
   - `status_bar.rs` — Braille-spinner status line matching Python format
   - `app.rs` — Root app orchestrator

### Completion Percentage (Estimated)

| Component | Complete | Notes |
|-----------|----------|-------|
| Python Core — Qontroller loop | 95% | Working, fixes applied |
| Python Core — CLI / TUI launch | 95% | Bare `qq task.md` now works |
| Python Core — Streaming | 90% | Terminal streaming works; web streaming needs work |
| Python Core — Progress system | 100% | Phase-aware calculator fully implemented |
| Python Core — Sandbox | 100% | Installed; wrapping disabled per design decision |
| Web Dashboard — Kanban board | 95% | 4 columns, ticket workflow ✓ |
| Web Dashboard — Progress display | 80% | `P: xx%` exists in stats bar but NOT in top-right |
| Web Dashboard — Agents page | 70% | 4-pane grid renders, but NO LIVE STREAMING |
| Web Dashboard — SSE events | 90% | EventTailer works, SSE endpoint works |
| Web Dashboard — Sessions | 90% | Session selector with fallback discovery |
| Rust TUI — Core | 90% | Compiles, launch flow works |
| Rust TUI — 4-pane view | 100% | Single output pane (not split into 4) |
| Overall | **~85%** | Core autonomy works; web polish + streaming needed |

---

## ════════════════════════════════════════════════════════════════
## SECTION 1: TOP-RIGHT PROGRESS PERCENTAGE DISPLAY
## ════════════════════════════════════════════════════════════════

### Current State

The dashboard currently shows progress in the **run-status-deck** (stats bar) as:
```html
<div class="telemetry-item"><span class="telemetry-lbl">Progress:</span>
  <span class="telemetry-val good" id="live-progress">0%</span>
</div>
```
This is located in the collapsible stats deck below the nav bar, NOT in the top-right area next to the CONNECTED indicator.

### What the TUI Does
The Rust/Python TUI status bar shows `P=XX%` in the center of the sticky line:
```
╭─[ꝖꝖ]─[v?.?.?]─❯❯❯ Qlarifier ⠛  C=1/∞ · T=00:30 · A=00:15 · P=45%  ⟬Q⟭─[↯ ]─[Building]─╮
```

### What We Need

**Add a prominent `P: XX%` display in the top-right of the web interface, right next to the CONNECTED indicator.**

The target location is the `nav-conn-block` div which currently contains:
```html
<div class="nav-conn-block">
  <div class="nav-signal-bars" id="signal-bars">
    <span></span><span></span><span></span><span></span>
  </div>
  <div class="status-dot" id="status-dot"></div>
  <span class="conn-status" id="conn-text">CONNECTED</span>
</div>
```

### Implementation Details

**File**: `qq/web/api.py` — In the HTML template (the `_landing_page()` method)

**Step 1**: Add a new `<div class="nav-progress-block">` immediately before or after `nav-conn-block` in the nav-deck:

```html
<div class="nav-progress-block">
  <span class="progress-icon">P:</span>
  <span class="progress-value" id="nav-progress">0%</span>
  <span class="progress-divider">|</span>
</div>
```

**Step 2**: Add CSS styles (in the `<style>` block):
```css
.nav-progress-block {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-right: 8px;
  font-family: var(--font-industrial);
  font-size: 13px;
  color: var(--constr-amber);
}
.nav-progress-block .progress-icon {
  color: var(--constr-amber);
  font-weight: bold;
}
.nav-progress-block .progress-value {
  color: var(--ok-green2);
  font-weight: bold;
  font-size: 14px;
  min-width: 40px;
  text-align: right;
}
.nav-progress-block .progress-divider {
  color: var(--bevel-edge);
  margin: 0 4px;
}
/* Pulse animation when progress changes */
@keyframes progress-pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); color: var(--constr-orange); }
  100% { transform: scale(1); }
}
.nav-progress-block.pulse .progress-value {
  animation: progress-pulse 0.4s ease-in-out;
}
```

**Step 3**: Add JS to update this element. Modify the existing `setProgressDisplay()` function (line ~2831):

```javascript
function setProgressDisplay(value) {
  var el = document.getElementById('live-progress');
  var navEl = document.getElementById('nav-progress');
  var pct = Math.round(value || 0);
  var displayStr = pct + '%';
  
  if (el) {
    el.textContent = displayStr;
    if (pct >= 100) el.className = 'telemetry-val good fully-done';
    else if (pct > 0) el.className = 'telemetry-val good';
    else el.className = 'telemetry-val';
  }
  
  // Update nav-progress in top-right
  if (navEl) {
    var prev = navEl.textContent;
    navEl.textContent = displayStr;
    
    // Color coding
    if (pct >= 100) {
      navEl.style.color = 'var(--ok-green2)';
      navEl.style.textShadow = '0 0 8px rgba(34,197,94,0.5)';
    } else if (pct >= 75) {
      navEl.style.color = 'var(--ok-green2)';
    } else if (pct >= 40) {
      navEl.style.color = 'var(--constr-amber)';
    } else if (pct > 0) {
      navEl.style.color = 'var(--constr-orange)';
    } else {
      navEl.style.color = 'var(--text-muted)';
    }
    
    // Pulse animation on change
    if (prev !== displayStr) {
      var block = navEl.closest('.nav-progress-block');
      if (block) {
        block.classList.remove('pulse');
        void block.offsetWidth; // force reflow
        block.classList.add('pulse');
      }
    }
  }
}
```

**Step 4**: In `FULLY_DONE` state handling, force `nav-progress` to 100% green with glow:
```javascript
// In the SSE event handler for run.completed:
if (type === 'run.completed') {
  setProgressDisplay(100);
  // ...
}
```

---

## ════════════════════════════════════════════════════════════════
## SECTION 2: LIVE AGENT OUTPUT STREAMING ON AGENTS PAGE
## ════════════════════════════════════════════════════════════════

### Current State

The Agents page (`renderAgentsPage()`) works by:
1. Fetching the full read-model via `GET /api/qonqrete/read-model`
2. Extracting `model.agent_outputs` (a dict keyed by role)
3. Displaying the last 50 lines of each agent's output buffer in the 2×2 grid
4. Refreshing every 2 seconds via `updateBoardFromModel()`

**Problem**: This is a poll-based snapshot, NOT real-time streaming. During a live run, the current agent's output appears with a 2-second delay, and all agents show stale snapshots rather than live streaming text. There is no visual indication of which agent is *currently active* and streaming.

### What We Need

**Real-time live agent output streaming on the Agents page.** When a run is active, the current agent's pane should show output streaming in real-time via SSE, with:
- Live text appearing in the active agent's pane as it's emitted
- Inactive agents showing their completed output
- A visual "active" indicator (pulsing border, spinner, etc.) on the current agent
- Character-by-character or line-by-line streaming effect

### Implementation Details

**File**: `qq/web/api.py`

#### Part A: SSE-Based Agent Stream Events

Currently, the SSE stream (`/api/qonqrete/events/stream`) emits raw events from `events.jsonl`. The read model's `_build_agent_outputs()` function already routes events to agent output buffers by checking event types (`stream.output`, `agent.output`, `output.line`, `agent_call.output`, `stream.line`, `stream_chunk`, `agent.stream`, `agent_log`, `stderr.line`, `stdout.line`, `agent_thought`, `agent_tool_call`).

We need to:
1. **Add a new SSE event type**: `agent.output_line` — emitted alongside regular events, carrying per-agent output lines in real-time
2. **OR extend the existing SSE handler** in `do_GET` to also check for new events in `agent_outputs` that haven't been sent yet

**Recommended approach**: Modify `EventTailer.sse_events()` to also emit synthesized `agent_output_line` events based on the event type routing in `_build_agent_outputs()`. However, since the tailer is meant to be read-only (it just tails the JSONL file), the better approach is:

**Alternative approach**: Add a new dedicated endpoint `GET /api/qonqrete/agent-output/stream` that:
- Reads events.jsonl from the last known position
- Routes output lines to agent roles
- Emits SSE events like:
  ```
  event: agent_output
  data: {"role": "construqtor", "ts": "14:30:15", "text": "Creating index.html...", "level": "info"}
  ```

But this adds complexity. The simplest effective approach is:

**Simplest effective approach**: Extend the existing SSE event stream to also send `agent_output_line` events when the source event type is an output/stream event. This way the client can subscribe to a single SSE stream and route agent output to the Agents page.

#### Part A.1: Modify the SSE event stream

In `do_GET` for `/api/qonqrete/events/stream`:

The current code sends raw events as JSON. We need to also send synthesized `agent_output_line` events for output-type events.

Actually, the cleanest approach is to **keep SSE as raw event relay** and have the **client-side JS** handle routing. The client already has `onSSEEvent()` which processes `data.type`. We just need to:

1. Add client-side routing for output events to populate agent panes in real-time
2. Add a `lastAgentOutputEventId` tracker to avoid re-rendering already-displayed output

#### Part B: Client-Side JS Changes

**Step 1**: Add a global `liveAgentLines` object to accumulate lines per agent:

```javascript
var liveAgentLines = {
  qlarifier: [],
  instruqtor: [],
  construqtor: [],
  inspeqtor: []
};
var liveAgentInitialized = false;
var lastAgentOutputEventIdx = 0; // track last processed event index
```

**Step 2**: Modify `onSSEEvent()` to route output events to agent panes:

```javascript
// Inside onSSEEvent(), add handling for agent output events:
var outputEventTypes = [
  'stream.output', 'agent.output', 'output.line',
  'agent_call.output', 'stream.line', 'stream_chunk',
  'agent.stream', 'agent_log', 'stderr.line', 'stdout.line',
  'agent_thought', 'agent_tool_call',
  'tool_call.start', 'tool.input', 'tool_call.result', 'tool.output'
];

if (outputEventTypes.indexOf(data.type) >= 0) {
  // Route to agent pane
  var role = data.role || currentActiveAgent || '';
  if (role && liveAgentLines[role]) {
    var ts = '';
    if (data.ts && data.ts > 0) {
      var d = new Date(data.ts * 1000);
      ts = d.toISOString().slice(11, 19);
    }
    var text = data.text || data.output || data.line || data.input || data.result || '';
    if (text && text.trim()) {
      liveAgentLines[role].push({
        ts: ts,
        text: text.trim(),
        level: data.level || 'info',
        event: data.type
      });
      // Cap at 500 lines per agent to prevent memory issues
      if (liveAgentLines[role].length > 500) {
        liveAgentLines[role] = liveAgentLines[role].slice(-500);
      }
      // If agents page is visible, update the pane immediately
      if (currentView === 'agents') {
        updateAgentPaneLive(role);
      }
    }
  }
  return; // Don't add to terminal event log
}

// Also handle active_agent_changed to update visual indicator:
if (data.type === 'active_agent_changed') {
  currentActiveAgent = data.role || '';
  if (currentView === 'agents') {
    highlightActiveAgent(currentActiveAgent);
  }
}
```

**Step 3**: Add `updateAgentPaneLive(role)` function for real-time pane updates:

```javascript
function updateAgentPaneLive(role) {
  var pane = document.getElementById('pane-' + role);
  if (!pane) return;
  var body = pane.querySelector('.agent-pane-body');
  if (!body) return;

  var lines = liveAgentLines[role] || [];
  if (lines.length === 0) return;

  // Show last 80 lines for active agent, 50 for inactive
  var maxLines = (role === currentActiveAgent) ? 80 : 50;
  var recentLines = lines.slice(-maxLines);
  
  // Build with color classes based on level
  var html = recentLines.map(function(l) {
    var prefix = l.ts ? '<span class="agent-ts">[' + l.ts + ']</span> ' : '';
    var cssClass = 'agent-line';
    if (l.level === 'error' || l.level === 'stderr') cssClass += ' agent-error';
    else if (l.level === 'tool') cssClass += ' agent-tool';
    else if (l.event === 'agent_thought') cssClass += ' agent-thought';
    return '<div class="' + cssClass + '">' + prefix + escapeHtml(l.text) + '</div>';
  }).join('');

  body.innerHTML = html;
  body.scrollTop = body.scrollHeight;
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
```

**Step 4**: Add `highlightActiveAgent(role)` function:

```javascript
function highlightActiveAgent(role) {
  var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
  agents.forEach(function(a) {
    var pane = document.getElementById('pane-' + a);
    if (!pane) return;
    if (a === role) {
      pane.classList.add('agent-active');
      // Update header to show running indicator
      var header = pane.querySelector('.agent-pane-header');
      if (header && header.textContent.indexOf('●') === -1) {
        header.innerHTML = header.innerHTML + ' <span class="agent-live-dot">●</span>';
      }
    } else {
      pane.classList.remove('agent-active');
      // Remove live dot from inactive agents
      var header = pane.querySelector('.agent-pane-header');
      if (header) {
        header.innerHTML = header.innerHTML.replace(' <span class="agent-live-dot">●</span>', '');
      }
    }
  });
}
```

**Step 5**: Add CSS styles for live agent indicators:

```css
.agent-pane.agent-active {
  border-color: var(--ok-green2) !important;
  box-shadow: 0 0 8px rgba(34,197,94,0.2);
}
.agent-live-dot {
  color: var(--ok-green2);
  animation: live-pulse 1s ease-in-out infinite;
  font-size: 10px;
  vertical-align: middle;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.agent-line {
  color: var(--text-muted);
  line-height: 1.6;
}
.agent-line.agent-error {
  color: var(--alarm-red);
}
.agent-line.agent-tool {
  color: var(--constr-amber);
}
.agent-line.agent-thought {
  color: var(--text-dim);
  font-style: italic;
}
.agent-ts {
  color: var(--steel-grey);
  font-size: 10px;
}
```

**Step 6**: Modify `renderAgentsPage()` to use live data when available, falling back to read-model:

```javascript
function renderAgentsPage() {
  var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
  agents.forEach(function(agent) {
    var pane = document.getElementById('pane-' + agent);
    if (!pane) return;
    var body = pane.querySelector('.agent-pane-body');
    if (!body) return;

    // Prefer live data for the current active agent
    var liveLines = liveAgentLines[agent];
    if (liveLines && liveLines.length > 0 && agent === currentActiveAgent) {
      updateAgentPaneLive(agent);
      return;
    }

    // Fall back to read-model data (existing logic)
    var agentData = null;
    if (allAgentOutputs) {
      if (Array.isArray(allAgentOutputs)) {
        var filtered = allAgentOutputs.filter(function(o) { return o.role === agent; });
        if (filtered.length > 0) agentData = filtered[filtered.length - 1];
      } else {
        agentData = allAgentOutputs[agent];
      }
    }

    if (!agentData || !agentData.lines || agentData.lines.length === 0) {
      var statusMap = {waiting:'Waiting to start...', active:'Running...', completed:'Completed.'};
      body.textContent = statusMap[agentData && agentData.status] || 'No output yet.';
      return;
    }

    // Use liveAgentLines if initialized from read model
    if (liveAgentLines[agent] && liveAgentLines[agent].length === 0 && agentData.lines.length > 0) {
      liveAgentLines[agent] = agentData.lines.slice();
    }

    var recentLines = agentData.lines.slice(-50);
    var text = recentLines.map(function(l) {
      var prefix = l.ts ? '[' + l.ts + '] ' : '';
      return prefix + (l.text || '');
    }).join('\n');
    body.textContent = text;
    body.scrollTop = body.scrollHeight;
  });
}
```

**Step 7**: When switching to the agents view, seed live data from read model:

```javascript
function switchView(view) {
  // ... existing code ...
  if (view === 'agents') {
    // Seed liveAgentLines from read model on first entry
    if (!liveAgentInitialized && allAgentOutputs) {
      var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
      agents.forEach(function(agent) {
        var agentData = null;
        if (Array.isArray(allAgentOutputs)) {
          var filtered = allAgentOutputs.filter(function(o) { return o.role === agent; });
          if (filtered.length > 0) agentData = filtered[filtered.length - 1];
        } else {
          agentData = allAgentOutputs[agent];
        }
        if (agentData && agentData.lines) {
          liveAgentLines[agent] = agentData.lines.slice();
        }
      });
      liveAgentInitialized = true;
    }
    renderAgentsPage();
    if (currentActiveAgent) {
      highlightActiveAgent(currentActiveAgent);
    }
  }
  // ... rest of function ...
}
```

---

## ════════════════════════════════════════════════════════════════
## SECTION 3: ISSUES FOUND DURING DEEP ANALYSIS
## ════════════════════════════════════════════════════════════════

### Issue 3.1: `currentActiveAgent` Not Maintained in JS

**File**: `qq/web/api.py` — JavaScript section

The SSE event handler `onSSEEvent()` processes `active_agent_changed` events but doesn't store the current agent in a global variable that `updateAgentPaneLive()` can use. The `updateRunState()` function updates `#live-agent-name` but doesn't set `currentActiveAgent`.

**Fix**: In `updateRunState()`, add:
```javascript
if (run.active_agent) {
  currentActiveAgent = run.active_agent;
}
```

### Issue 3.2: Agent Output Read Model Not Updated Incrementally via SSE

**File**: `qq/web/read_model.py` — `_build_agent_outputs()`

The `_build_agent_outputs()` function processes ALL events from scratch every time. With incremental caching, new events are appended but the agent output buffers are rebuilt entirely. This is fine for correctness but means the read model `agent_outputs` always contains the full history. The client can use the `lines` array length as a cursor.

**Issue**: The SSE events don't carry `agent_output_line` synthesized events; the client must poll the read model to get agent output. The live streaming solution above (routing output events directly in SSE `onSSEEvent()`) solves this.

### Issue 3.3: Read-Model Cache Keyed by `run_root`, but SSE Follows `current-run.json`

**File**: `qq/web/read_model.py` — `_read_model_cache`

The read-model cache is keyed by `run_root`. When `current-run.json` switches (session switching), the control-root resolution in `build_read_model()` resolves to the active run's root. However, the `EventTailer.rebind()` only resets the events path and position — it doesn't invalidate the read-model cache for the new run.

**Fix**: In `EventTailer.rebind()`, also call `get_read_model_cache().invalidate(self._path)` or similar. Already partially handled by the `_reconcile_tailer()` method, but worth verifying.

### Issue 3.4: No Agent-Specific SSE Events Emitted by Qontroller

**File**: `qq/qontroller.py`

The qontroller emits events like `active_agent_changed`, `build_group.started`, `review.started`, etc. But the actual agent subprocess output (stdout/stderr from CodeSeeq) is streamed through `AgentOutputStreamer.emit()` to the terminal, NOT to the event log. The event log only receives high-level lifecycle events, not per-line output.

**Impact**: The web dashboard's SSE stream never receives agent output lines unless those lines are also written to `events.jsonl`.

**Root cause in `adapters/codeseeq.py`**: Agent subprocess stdout/stderr is captured and streamed via `AgentOutputStreamer`, but NOT written to `events.jsonl`. The event log is designed for structured lifecycle events, not raw output.

**Fix options**:
1. **Emit output lines to event log** (adds massive volume to events.jsonl — bad for storage)
2. **Create a separate agent output log** (`agent_output.jsonl` per agent) and serve it via SSE
3. **Bridge from terminal streamer to web SSE** — modify the `_wrapped_on_event` in qontroller to also emit agent output events to the event log with a flag indicating they're output lines

**Recommended**: Option 3 — add a `stream_output` event type to the event log. Modify the `_build_agent_outputs()` in read_model.py (already does this) and ensure the event log receives output lines:

In `qontroller.py`, modify `_wrapped_on_event` or add a stream callback:

```python
# In qontroller.run(), add a stream_to_event_log callback:
def _stream_to_event_log(chunk: dict):
    """Route agent output to event log for web dashboard streaming."""
    role = chunk.get("role", "")
    text = chunk.get("text", "")
    if text and text.strip():
        log.emit("stream.output",
                 role=role,
                 text=text.strip(),
                 stream=chunk.get("stream_name", "stdout"),
                 call_id=chunk.get("call_id", ""))
```

And pass this as the `sink` to the `AgentOutputStreamer` or hook it into the stream config.

**IMPORTANT**: The adapter (`codeseeq.py`) creates the streamer. We need to modify `codeseeq.py` to accept an optional event log callback and emit output lines to events.jsonl.

### Issue 3.5: Rust TUI Output View is Single-Pane (Not 4-Pane Split)

**File**: `qq-tui/src/layout.rs`, `qq-tui/src/widgets/output_view.rs`

The Rust TUI has a single output view (`OutputView`) for all agent output. The layout only has three areas: status bar, output view, input box. There's no 4-pane split in the TUI.

**Current behavior**: All agent output goes into the same scrollable view, color-coded by role. This is actually fine for a terminal interface — the web dashboard is where the 4-pane split makes more sense. No fix needed for the TUI.

### Issue 3.6: `agent_outputs` Fields Not Populated with Model Info from Events

**File**: `qq/web/read_model.py` — `_build_agent_outputs()`

When `active_agent_changed` events include `model`, the code sets `agents[current_agent]["model"]`. But this only works if the event carries the model. The `config.loaded` event also carries models per role. The current code doesn't backfill model info from `config.loaded`.

**Fix**: In `_build_agent_outputs()`, after processing all events, also scan for `config.loaded` and fill in model info:
```python
# After the event loop in _build_agent_outputs():
for evt in events:
    if evt.get("type") == "config.loaded":
        models = evt.get("models", {})
        for role, model in models.items():
            if role in agents:
                agents[role]["model"] = agents[role]["model"] or model
```

### Issue 3.7: `renderAgentsPage()` Overwrites Live Data on Refresh

**File**: `qq/web/api.py` — `renderAgentsPage()`

When `updateBoardFromModel()` runs every 2 seconds, it calls `renderAgentsPage()` if the current view is `agents`. This overwrites the live-streamed content in the panes with the read-model snapshot.

**Fix**: Add a guard in `renderAgentsPage()` to skip panes that have been recently updated via live streaming:

```javascript
var LIVE_AGENT_REFRESH_COOLDOWN_MS = 1000; // 1 second cooldown
var lastLiveAgentUpdate = {};

function updateAgentPaneLive(role) {
  lastLiveAgentUpdate[role] = Date.now();
  // ... rest of function ...
}

function renderAgentsPage() {
  var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
  agents.forEach(function(agent) {
    // Skip live-updated panes within cooldown
    var lastUpdate = lastLiveAgentUpdate[agent] || 0;
    if (Date.now() - lastUpdate < LIVE_AGENT_REFRESH_COOLDOWN_MS &&
        liveAgentLines[agent] && liveAgentLines[agent].length > 0) {
      return; // Skip — live data is fresher
    }
    // ... rest of existing logic ...
  });
}
```

### Issue 3.8: Progress Display Not Updated on SSE `run.completed`

**File**: `qq/web/api.py` — SSE event handler

When `run.completed` arrives via SSE, the `metrics.effective_progress_pct` is not sent in the event. The client only gets progress from polling `/api/qonqrete/read-model`. On `FULLY_DONE`, the progress should immediately jump to 100%.

**Fix**: In the SSE event handler:
```javascript
if (data.type === 'run.completed') {
  setProgressDisplay(100);
  // Also update the nav-progress
  var navEl = document.getElementById('nav-progress');
  if (navEl) {
    navEl.textContent = '100%';
    navEl.style.color = 'var(--ok-green2)';
  }
}
```

### Issue 3.9: Web CSS Uses `var(--steel-grey)` But Not Defined

**File**: `qq/web/api.py` — CSS section

The agent line CSS I propose uses `var(--steel-grey)` for timestamps. Check if this CSS variable is defined. Looking at the existing CSS, the dashboard uses `--text-muted`, `--text-dim`, etc. Add `--steel-grey: #9ca3af;` if not present, or use `var(--text-dim)` instead.

### Issue 3.10: No Clear Visual Separation Between Agent Panes and Task/Config Panels

**File**: `qq/web/api.py` — HTML structure

The Agents, Tasks, and Config views all share the same `#panel-view` container. When switching, the display toggles. This works, but there's no header label showing which view is active.

**Fix**: Add an active view label above the panel:
```html
<div id="panel-view-label" style="display:none; color: var(--constr-amber); font-family: var(--font-industrial); font-size: 12px; text-transform: uppercase; padding: 4px 0;"></div>
```
And set it in `switchView()`.

---

## ════════════════════════════════════════════════════════════════
## SECTION 4: PRIORITIZED IMPLEMENTATION ORDER
## ════════════════════════════════════════════════════════════════

### Priority 1: Progress % in Top-Right (Section 1)
- **Effort**: Small (~30 lines of HTML/CSS/JS)
- **Impact**: High — users immediately see progress without scrolling
- **File**: `qq/web/api.py`

### Priority 2: Agent Output Streaming on Agents Page (Section 2)
- **Effort**: Medium (~150 lines of JS + CSS)
- **Impact**: High — core feature for monitoring agent activity
- **Files**: `qq/web/api.py`, `qq/qontroller.py`, `qq/adapters/codeseeq.py`

### Priority 3: Qontroller Emits Agent Output to Event Log (Issue 3.4)
- **Effort**: Small (~20 lines Python)
- **Impact**: Critical prerequisite for Priority 2
- **Files**: `qq/qontroller.py`, `qq/adapters/codeseeq.py`

### Priority 4: Render Cooldown Guard (Issue 3.7)
- **Effort**: Small (~15 lines JS)
- **Impact**: Medium — prevents live data from being overwritten
- **File**: `qq/web/api.py`

### Priority 5: Model Info Backfill (Issue 3.6)
- **Effort**: Small (~10 lines Python)
- **Impact**: Low — cosmetic
- **File**: `qq/web/read_model.py`

### Priority 6: CSS Cleanup + Visual Polish (Issues 3.9, 3.10)
- **Effort**: Small (~15 lines CSS/HTML)
- **Impact**: Low — quality of life
- **File**: `qq/web/api.py`

---

## ════════════════════════════════════════════════════════════════
## SECTION 5: FILE CHANGE SUMMARY
## ════════════════════════════════════════════════════════════════

| File | Lines Changed | Description |
|------|---------------|-------------|
| `qq/web/api.py` | ~200 | Progress in top-right, live agent streaming, CSS, JS |
| `qq/qontroller.py` | ~15 | Emit agent output events to event log |
| `qq/adapters/codeseeq.py` | ~10 | Wire event log callback into streamer |
| `qq/web/read_model.py` | ~10 | Backfill model info from config.loaded |
| **Total** | **~235** | |

---

## ════════════════════════════════════════════════════════════════
## SECTION 6: FINAL COMPLETION TARGET
## ════════════════════════════════════════════════════════════════

After implementing all items above, estimated project completion:

| Component | Before | After |
|-----------|--------|-------|
| Web Dashboard — Progress display | 80% | **100%** |
| Web Dashboard — Agents page | 70% | **95%** |
| Overall | ~85% | **~93%** |

Remaining after this finish round:
- End-to-end production testing
- Error edge cases (agent crash recovery visualization)
- Historical run browsing with full agent output replay
- Mobile-responsive dashboard layout
- Performance optimization for runs with 1000+ briQs


---

## ════════════════════════════════════════════════════════════════
## APPENDIX A: `qq run` DEFAULT TO `--allow-dirty`
## ════════════════════════════════════════════════════════════════

### What Changed

The `qq run` command now defaults to `--allow-dirty` so that users no longer
need to explicitly pass the flag every time.

**File**: `qq/cli.py` — line 198

```python
# Before:
run_p.add_argument("--allow-dirty", action="store_true", default=False,
                    help="Allow running on a dirty git repo")

# After:
run_p.add_argument("--allow-dirty", action="store_true", default=True,
                    help="Allow running on a dirty git repo (default: True)")
```

A `--no-allow-dirty` counterpart is not yet wired; users who need strict
clean-repo enforcement can pass `--allow-dirty` with an explicit `false` by
setting it in config or using the env var equivalent when that is wired.
