# QonQrete Ultimate Finish Prompts — Web UI + TUI Finishing Upgrades

> **Scope:** Maximum-detail, implementation-ready upgrade specifications for the
> QonQrete Web Dashboard ("briQsQope") and the Rust TUI cockpit ("qq-tui").
> Every instruction below is grounded in the actual codebase: file paths, function
> names, HTML element IDs, CSS variables, JS render functions, Rust struct fields,
> and `format!` strings are all real and locatable so each item can be executed
> end-to-end without guesswork.

---

## Zero — Ground Truth & Code Map (read this first)

Before touching anything, confirm the current state against these anchors so every
edit lands on the right symbol:

### Web Dashboard — `qq/web/api.py`
This single file contains the entire frontend. Key regions:

| Concern | Location / Symbol |
|---|---|
| Navigation tabs (top menu) | `<div class="nav-tabs">` → `<button ...>Dashboard</button>`, `Agents`, `Tasks`, `Config`, `Sessions`. |
| Page/view label ("double indicator") | `<div id="panel-view-label">Dashboard</div>` (parentheses text auto-set by JS). |
| Connection block (top-right) | `<div class="nav-conn-block">` → `#signal-bars`, `#status-dot`, `#conn-text` (`CONNECTED`). Rendered by `setConnectionStatus(status)`. |
| Progress block (top-right) | `<div id="nav-progress-block">` → `.nav-progress-icon` (`P:`), `#nav-progress` (`0%`). |
| Run telemetry deck | `<div id="current-run-panel">` → `#statsbar` telemetry items: `#live-run-id`, `#live-status`, `#live-agent-name`, `#live-model`, `#live-action`, `#live-cycle`, `#live-total-time`, `#live-progress`, `#live-groups-done`, `#live-total-groups`, `#live-briqs-done`, `#live-total-briqs`. |
| Agents panel | `#agents-panel` → `.agent-grid` → `#pane-qlarifier`, `#pane-instruqtor`, `#pane-construqtor`, `#pane-inspeqtor`. Rendered by `renderAgentsPage()`. |
| Tasks panel | `#tasks-panel` → `#tasks-original`, `#tasks-enhanced`, `#tasks-groups` (Build Groups — **remove this**). |
| Config panel | `#config-panel` → `#config-content`. Filled by `loadConfig()`. |
| Bottom instrument deck | `.bottom-instrument-deck` → `#terminal` (event log), `.big-mascot-area` (mascot image `qonqrete-bottom-right.jpg`), `.system-side-rail`. |
| Deck resizer / scaling | `applyBottomDeckHeight(h)`, `calculateDeckResizeBounds()`. Mascot width scales via `bigArea.style.width`. |
| Overlay system | `#overlay` / `#overlay-content`, helper `openGroupOverlay(gid)`. |
| Live polling | `updateBoardFromModel()`, `renderAgentsPage()`, the `setInterval` poll loop that fetches `/api/qonqrete/...`. |

### TUI Cockpit — `qq-tui/src/`
| Concern | Location / Symbol |
|---|---|
| Status state model | `qq-tui/src/status.rs` → `struct StatusState` fields: `model_code`, `cycle`, `max_cycles`, `progress: Option<f64>`, `action_status: Option<String>`, `session_started_at`, `active_started_at`, `accumulated_active`, `phase`, etc. |
| Time helpers | `total_elapsed()`, `total_elapsed_secs()`, `active_time()`, `active_secs()`, `fmt_elapsed(secs)`, `fmt_active(secs)`, `fmt_duration(secs)`. |
| Status bar renderer | `qq-tui/src/widgets/status_bar.rs` → `build_builtin_bar()` + `paint_colored_segments()`. The literal strings `"Cyc={cycle}/{max_display}"`, `"Total={total}"`, `"Agent={active}"`, `"P{approx}{pct}%"` are built here. |
| Model abbreviation | `model_display_code(&str) -> String` in `status_bar.rs` (maps e.g. `deepseek-v4-flash` → `fla`). |
| Action status wiring | `self.status.action_status = Some(action)` in `app.rs` (two event-loop locations, ~line 635 and ~line 749). |
| Loop/event ticks | `main_event_loop(...)` and the secondary loop in `app.rs`; spinner/status refresh timers. |

---

# PART A — WEB DASHBOARD UPGRADES (15 items)

---

## A1 — Rename top-menu buttons

**Target:** `<div class="nav-tabs">` in `qq/web/api.py`.

**Requirement:** Two button labels change. Keep the `id` attributes and `onclick`
handlers **exactly** as they are so view switching keeps working.

| Before | After | Keep unchanged |
|---|---|---|
| `Dashboard` | `BOARD` | `id="nav-dashboard"`, `onclick="switchView('dashboard')"`, `class="nav-tab"` |
| `Sessions` | `RUNS` | `id="nav-sessions"`, `onclick="openSessionSelector()"`, inline `style="color:var(--constr-amber)"` |

**Accuracy notes:**
- `Sessions` currently carries an inline amber `style`; keep that color on the renamed `RUNS` button.
- Do **not** change the `switchView('dashboard')` / `switchView('agents')` /
  `switchView('tasks')` / `switchView('config')` targets — only the visible text.
- Also update any JS that matches buttons by their old label text (e.g. an
  `aria-label`, or a `textContent` comparison in the view-switch logic). Grep for
  the literal strings `"Dashboard"`, `"Sessions"` and change only the
  user-facing occurrences, not the `switchView()` arguments.

---

## A2 — Replace the CONNECTED/signal-bars block with a live ACTION bar

**Target:** `#nav-conn-block` (contains `#signal-bars`, `#status-dot`, `#conn-text`)
and the `setConnectionStatus(status)` JS function.

**Requirement:** Remove the connection indicator entirely and repurpose that
top-right slot to display the **current action**, mirroring the TUI's
`Act:Planning`, `Act:Clarifying`, `Act:Building`, `Act:Reviewing`.

**Implementation recipe (precise):**

1. Replace the inner HTML of `.nav-conn-block` with a single action element:
   - New element: `<span class="nav-action-label" id="nav-action" style="...">Act:Planning</span>`.
   - Keep the wrapper `.nav-conn-block` (or rename to `.nav-action-block`) so the
     layout flex positioning is preserved and nothing else breaks.

2. Introduce/repurpose a JS function (rename `setConnectionStatus` → `setActionStatus`):
   ```js
   function setActionStatus(action) {
     var el = document.getElementById('nav-action');
     if (!el) return;
     if (!action || action === 'idle' || action === 'Waiting for run') {
       el.textContent = 'Act:Waiting';
       el.className = 'nav-action-label idle';
     } else {
       el.textContent = 'Act:' + action;
       el.className = 'nav-action-label active';
     }
   }
   ```

3. Feed it from the same source that already fills `#live-action` in the telemetry
   deck (`updateBoardFromModel()` uses `run.action_status`). Update `#nav-action`
   in the **same code path** that sets `#live-action`, so the top-right bar and
   the telemetry "Action:" value stay perfectly in sync.

4. Delete the now-unused code **without breaking anything else**:
   - Remove `setConnectionStatus()` definition and its call sites.
   - Remove `#signal-bars`, `#status-dot`, `#conn-text` references.
   - Do **not** remove the actual fetch/reconnect plumbing; only the indicator
     UI. If `setConnectionStatus` also drove `.nav-signal-bars.err` styling for
     reconnecting states, fold that signal into `#nav-action` (e.g. add an
     `err` class that turns the label red during reconnect so you don't silently
     lose failure visibility).

**Acceptance:** No "CONNECTED" text, no signal bars, no status dot. The top-right
block now always reads `Act:X`, where `X` tracks Planning/Clarifying/Building/
Reviewing/Waiting/etc., and it updates live without breaking the poll loop, the
fetch retry, or any other header element.

---

## A3 — Replace `P: XX%` with `PROGRESS: XX%`

**Target:** `#nav-progress-block` in `qq/web/api.py`.

**Requirement:** The top-most-right progress label changes from `P:` to `PROGRESS:`.

**Implementation:**
- `.nav-progress-icon` currently renders `P:`. Change its text to `PROGRESS:`.
- Adjust the CSS width/padding for `.nav-progress-icon` so the longer label does
  not wrap or overflow the header (the header is flex; allow the block to widen,
  or reduce letter-spacing/font-size slightly). Keep `#nav-progress` value
  (`0%` → live percentage) and `.nav-progress-divider` (`|`) untouched.
- Ensure the value update logic (wherever it sets `#nav-progress` text from
  `effective_progress_pct`) is unaffected.

**Acceptance:** Reads `PROGRESS: 37%` (or whatever live value), no `P:` remnant.

---

## A4 — Remove the duplicate page/menu indicator

**Target:** `#panel-view-label` (the small uppercase text that echoes the current
view name) plus the JS that sets its text.

**Requirement:** Delete it because the active menu tab is already highlighted
yellow (`.nav-tab.active`), making the duplicate label pointless.

**Implementation recipe:**
1. Remove `<div id="panel-view-label" ...>Dashboard</div>` from the HTML.
2. Find every JS reference to `panel-view-label` (grep `panel-view-label`) and
   remove the assignment lines inside `switchView(...)` / view toggling.
3. Confirm `switchView()` still sets `.active` on the correct `nav-tab` button
   (that is the single source of truth for "where am I") and that no other
   layout depends on `panel-view-label`'s height/padding.

**Acceptance:** Only the yellow-highlighted tab communicates the current page.
No stray empty `<div id="panel-view-label">` and no JS errors.

---

## A5 — Clickable agent terminals → full-screen live-tail overlay

**Target:** The four panes in `#agents-panel` (`#pane-qlarifier`, `#pane-instruqtor`,
`#pane-construqtor`, `#pane-inspeqtor`), plus the existing `#overlay` system.

**Requirement:** Clicking any one of the 4 agent terminals opens an overlay showing
**only that agent's output**, live-following/tailing. A close "✕" exits the overlay.

**Implementation recipe (precise):**

1. Make each pane clickable:
   - Add `style="cursor:pointer"` to each `.agent-pane`.
   - Add a click handler (onclick or event delegation) that resolves the agent role:
     `openAgentOverlay('qlarifier')`, `('instruqtor')`, `('construqtor')`, `('inspeqtor')`.

2. Reuse the existing overlay scaffold. New helper `openAgentOverlay(role)`:
   ```js
   function openAgentOverlay(role) {
     var ov = document.getElementById('overlay');
     var content = document.getElementById('overlay-content');
     var label = { qlarifier:'Qlarifier', instruqtor:'instruQtor',
                   construqtor:'construQtor', inspeqtor:'inspeQtor' }[role];
     ov.style.display = 'flex';
     content.innerHTML =
       '<div class="overlay-agent-header">' +
         '<span>' + label + ' — LIVE TAIL</span>' +
         '<button class="overlay-close" onclick="closeAgentOverlay()">✕</button>' +
       '</div>' +
       '<pre class="overlay-agent-body" id="overlay-agent-body">' +
         escapeHtml(agentOutputText(role)) +
       '</pre>';
     startAgentTail(role);
   }
   ```
3. `agentOutputText(role)` must read from the **same data source** that
   `renderAgentsPage()` uses (the read-model `agent_outputs` dict keyed by role,
   with each entry exposing a `lines` array). Return the concatenated text for that
   role only.
4. `startAgentTail(role)` runs a short `setInterval` (e.g. 500ms) that refetches the
   latest output for `role` and appends/rewrites `#overlay-agent-body`, always
   `scrollTop = scrollHeight`. On overlay close, `clearInterval` the tail timer.
5. `closeAgentOverlay()` hides `#overlay`, clears the interval, and restores the
   underlying `renderAgentsPage()` state. The existing `#overlay` click-outside or
   Escape handling (if any) must also call `closeAgentOverlay()`.

**Acceptance:** Click pane → overlay with only that agent's stream, live-tailing;
click ✕ (or Escape/click-outside if present) → back to the 2×2 grid with no
leaked timers or duplicated DOM.

---

## A6 — Per-agent terminal colors (cyan / pink / yellow / green on black)

**Target:** `renderAgentsPage()` output and the `.agent-pane-body` / `.agent-grid`
CSS in `qq/web/api.py`.

**Requirement — exact palette (all on a near-black `#000000` / `#0a0a0a` background):**

| Pane | Agent | Text color |
|---|---|---|
| 1 | Qlarifier | **cyan** |
| 2 | instruQtor | **pink** |
| 3 | construQtor | **yellow** |
| 4 | inspeQtor | **green** |

**Implementation recipe:**
1. Add/assign a per-role CSS class (e.g. `.agent-pane.qla .agent-pane-body { color: var(--cyan-accent); background:#000; }` and analogous `.ins`, `.con`, `.spq`).
   Map roles to classes: Qlarifier→cyan, instruQtor→pink, construQtor→yellow, inspeQtor→green.
2. In `renderAgentsPage()`, when generating each pane body, set the body's class
   (or a span inside it) to the role-specific color class. Do **not** rely on
   agent order alone — key off the explicit `role` name from the read-model so
   colors stay correct even if the dict order changes.
3. Ensure `background: #000000` (or a very dark `#0a0a0a`) is applied to each
   `.agent-pane-body` so the colored text has the requested black terminal backdrop.
4. Verify the live-tail overlay (A5) reuses the exact same per-role color for
   consistency (cyan/pink/yellow/green respectively, black background).

**Acceptance:** Four terminals each render with their assigned color on black;
colors survive live updates and the overlay.

---

## A7 — Remove "Build Groups" from the Tasks page

**Target:** `#tasks-groups` section (`<div class="task-section" id="tasks-groups">...`)
and any JS that populates `#tasks-groups-list`.

**Requirement:** Delete the Build Groups block entirely; keep only the two task panes.

**Implementation recipe:**
1. Remove the whole `#tasks-groups` `<div class="task-section">...</div>` from the
   Tasks panel markup.
2. Grep and remove `tasks-groups` / `tasks-groups-list` references in JS (the code
   that renders group items), and any `allGroups`/group-fetch path that **only**
   served this panel. Do not break the Dashboard kanban's use of groups/briqs.

**Acceptance:** Tasks page shows only "Original Task" and "Enhanced Task";
no empty Build Groups section, no JS errors from missing `#tasks-groups-list`.

---

## A8 — Tasks page: full-height vertical split (Original top / Enhanced bottom)

**Target:** `#tasks-panel` and its `#tasks-original` + `#tasks-enhanced` sections.

**Requirement:** Split the screen in half vertically:
- **Top half:** Original Task, with its own independent scrollbar.
- **Bottom half:** Enhanced Task, with its own independent scrollbar.
- Clicking a pane focuses it; scrolling then operates on the **focused** pane only.

**Implementation recipe:**
1. Make `#tasks-panel` a full-height flex column with no gap overflow:
   `display:flex; flex-direction:column; height:100%; overflow:hidden;`.
2. Give each `task-section` `flex:1 1 50%; min-height:0; display:flex; flex-direction:column;`.
3. Make each `.task-content` scrollable and fill its half:
   `flex:1 1 auto; overflow-y:auto; min-height:0; word-break:break-word;`.
4. Focus model:
   - Track a single `focusedTaskPane` variable (default `original`).
   - Add click handlers to both `#tasks-original` and `#tasks-enhanced` that set
     `focusedTaskPane` and add a visual focus ring/class (e.g. `.task-content.focused`).
   - Since native scroll wheel scrolls whichever element is under pointer
     (the browser default already scrolls the hovered scroll container),
     the "click to focus" primarily needs to: (a) ensure the clicked pane becomes
     the keyboard-scroll target via `el.focus()`/`tabindex="0"`, and (b) apply the
     visible focus styling. Do not block default wheel behavior.
5. Both panes must show full content with their own `scrollTop`-based scrollbars;
   do not let one pane's overflow push the other off-screen.

**Acceptance:** 50/50 split, two independent scrollbars, click-to-focus highlights
the active pane, keyboard/wheel scroll affects the focused pane.

---

## A9 — Config page: darker, near-black background

**Target:** `#config-panel`, `#config-content`, and the `--bg`/panel CSS variables
used by the config view.

**Requirement:** Make the config view background noticeably darker — a dark grey
almost black — for readability.

**Implementation:**
- Set the config panel/content background to near-black (e.g. `#0b0b0d` to
  `#111`) with sufficient contrast against the foreground.
- Update the config `pre`/JSON code colors to remain readable on the darker
  background (adjust muted text / key / string / number tones as needed).
- Scope the change to the config panel so the rest of the dashboard's construction-
  yard theme is not unintentionally darkened.

**Acceptance:** Config JSON is comfortably readable on an almost-black background.

---

## A10 — Add Total time + Agent time blocks next to PROGRESS

**Target:** The top-right run telemetry — specifically the `#current-run-panel`
`#statsbar` area and/or `#nav-progress-block` region.

**Requirement:** Next to the `PROGRESS: XX%` block, add two more blocks:
- `Total: XX:XX` (MM:SS, or HH:MM:SS once it exceeds one hour)
- `Agent: XX:XX` (same format)

Mirroring the TUI's `Total=` and `Agent=` fields.

**Implementation recipe:**
1. The read-model already carries these values; the dashboard needs to surface them:
   - **Total** = total session wall-clock (session start → now), freezing at
     FULLY_DONE per A15.
   - **Agent** = current agent active time (resets on each handoff
     Qlarifier → instruQtor → construQtor → inspeQtor), i.e. equivalent to
     `active_secs()`/`reset_active_time()` semantics in the TUI.
2. Add telemetry items near `#nav-progress`:
   - `<span class="telemetry-lbl">Total:</span><span class="telemetry-val" id="live-total-time">00:00</span>` (already exists as `#live-total-time` — **wire it**).
   - `<span class="telemetry-lbl">Agent:</span><span class="telemetry-val" id="live-agent-time">00:00</span>` (new `#live-agent-time`).
3. Update the poll loop to compute and write both values every tick using a source
   timestamp (from the run/session model), cleaning the plural/`:` format exactly
   like TUI `fmt_elapsed`/`fmt_active`. Use a JS formatter shared by both web values
   and keep it monotonic (a cached `startedAt` epoch so the clock never jumps
   backwards after a fetch).
4. Place them directly adjacent to the `PROGRESS` block in reading order
   `Total · Agent · Progress` (or as the spec phrases "next to PROGRESS"), keeping
   the header compact so nothing wraps on a normal desktop width.

**Acceptance:** Two new blocks read `Total: 12:34` and `Agent: 03:21` and tick live;
agent resets on each agent handoff; total freezes at FULLY_DONE.

---

## A11 — QQ version number on bottom-right below the squid

**Target:** `.big-mascot-area` (mascot image `qonqrete-bottom-right.jpg`) and the
`.system-side-rail` / bottom deck in `qq/web/api.py`.

**Requirement:** Display the QQ version number on the bottom-right, directly below
the squid, bottom-center aligned to the squid. It must **resize along with the
squid** when the deck is resized.

**Implementation recipe:**
1. Determine the canonical version source (package `__version__`, `pyproject.toml`,
   or the read-model's version field) and expose it to the frontend (add it to an
   existing JSON endpoint or inject it into a `data-version` attribute on a root node).
2. Add a version element **inside/attached to** `.big-mascot-area` so it sits
   immediately beneath the mascot image and is vertically centered under it:
   `<div class="mascot-version" id="mascot-version">vX.Y.Z</div>`.
3. Tie its size to the same scalar that `applyBottomDeckHeight(h)` uses when it
   sets `bigArea.style.width` (`scaledW = clamp(h * 0.9, 80, 180)`). Compute a
   `font-size` proportional to `scaledW` (e.g. `fontSize = `${Math.max(9, scaledW * 0.14)}px``)
   and apply it to `#mascot-version` in the **same** `applyBottomDeckHeight()`
   function so resizing the mascot resizes the version label in lock-step.
4. Position: bottom-right region, text centered horizontally under the squid.

**Acceptance:** Version label appears under the squid, bottom-center, and scales
proportionally whenever the deck resizer is dragged.

---

## A12 — `Cycle=1/∞` on the top bar (renamed from "Cyc")

**Target:** Top bar telemetry: `#live-cycle` (`Cycle:` label + `—/—` value) and the
TUI center `Cyc=...` (handled in Part B).

**Requirement (web side):** Rename the `"Cyc"`-style prefix to `"Cycle"` and render
`Cycle=1/∞`, bumping the left number `+1` each time inspeQtor hands the reviewed
output back to construQtor (i.e. at the exact completion of a review→build handoff,
the cycle increments).

**Implementation recipe:**
1. Change the display label from any short `Cyc` form to `Cycle=` (or keep the
   existing `Cycle:` label but ensure it renders the `1/∞` value form).
2. Locate the read-model field that denotes a completed cycle (likely `run.cycle`
   incremented when the inspeQtor→construQtor handoff completes). Confirm the
   increment point in the backend (`qq/qontroller.py`) is the review-handoff event,
   not an unrelated status change. If it currently increments at the wrong point,
   move it to the **reviewer-returns-to-builder** transition exactly.
3. Ensure `max_cycles` of `0` or unset renders as `∞` (U+221E), preserving the
   existing `max_cycles_display` fallback logic already in `updateBoardFromModel()`.
4. `build_builtin_bar`-equivalent web code must show `Cycle=1/∞` (left number = `run.cycle`).

**Acceptance:** Web top bar shows `Cycle=1/∞`, increments by exactly 1 per
review→build handoff, and renders `∞` when unbounded.

---

## A13 — Show the active model abbreviation (`[fla]`) in the top bar

**Target:** Top bar / telemetry (web: `#live-model` in `#statsbar`; TUI: the
`[{model}]` segment in `status_bar.rs`).

**Requirement:** Display the **abbreviated** model code exactly like the TUI does
(e.g. `[fla]`, `[fla-T]`, `[pro]`, `[pro-T]`), not the full model name.

**Implementation recipe (web):**
1. Add a frontend mirror of the TUI's `model_display_code()` mapping:
   - `fla` / "flash" (not "thinking") → `fla`
   - `fla-T` / "flash-thinking" → `fla-T`
   - `pro` / "pro" → `pro`
   - `pro-T` / "pro-thinking" → `pro-T`
   - Idempotent: if already a short code, return as-is.
2. Apply this mapping when setting `#live-model` so it reads `[fla]` (bracket
   wrappers can be CSS or literal). Keep the raw full model accessible elsewhere
   if the config view needs it; only the top bar uses the abbreviation.
3. Ensure the model refreshes with the same poll as A2/A10.

**TUI note:** Already implemented via `model_display_code()` and the
`[{model}]` segment in `build_builtin_bar()`; verify it stays correct after Part B
text edits (A3/B1 renames must not disturb the `[{model}]` right segment or its
gold paint in `paint_colored_segments()`).

**Acceptance:** Top bar shows `[fla]` style abbreviation (web and TUI), no full
`deepseek-v4-flash` name in the status area.

---

## A14 — Braille-snake loader above the squid (bottom-right)

**Target:** `.big-mascot-area` area in `qq/web/api.py` — positioned above the squid
and centered to it, resizing along with the squid.

**Requirement:** A sideways **braille-snake** spinner (a single-cell row of braille
dot characters cycling through frames, oriented horizontally) just above the squid,
to show "activity / we are progressing." It must resize together with the squid.

**Implementation recipe:**
1. Braille spinner frames (sideways/horizontal braille snake). Use a frame list of
   braille dot glyphs that convey a slithering motion across a short run, e.g.:
   ```js
   var BRAILLE_SNAKE = [
     '⣀', '⣄', '⣆', '⣇', '⣧', '⣷', '⣿', '⣾', '⣶', '⣧', '⣇', '⣆', '⣄', '⣀', '⠀'
   ];
   ```
   (pick a monotonic sequence where the "body" travels left-to-right, holding a
   small window of glyphs or rendering a fixed-width segmented snake; the intent is
   a horizontal "slither" loader, not the vertical `⠁⠂⠄⡀⢀⠠⠐⠈` dot spinner.)
2. Add `<div class="mascot-loader" id="mascot-loader" aria-hidden="true"></div>`
   **above** the mascot image, centered horizontally (`text-align:center`) and
   sitting just above it inside `.big-mascot-area`.
3. Animate: a `setInterval` (e.g. 100–150ms) cycles `BRAILLE_SNAKE` frames and
   writes the glyph into `#mascot-loader`. Drive it from the same "is running /
   activity" signal used by the spinner elsewhere; freeze/clear it at terminal state.
4. Resize lock-step: in `applyBottomDeckHeight(h)`, after setting `bigArea.style.width`,
   set `#mascot-loader` `font-size` proportional to the same `scaledW` (e.g.
   `Math.max(10, scaledW * 0.12)` px) so it scales with the squid.
5. Centered to the squid horizontally; "sideways" means the snake is drawn left→right.

**Acceptance:** A horizontal braille snake animates above the squid whenever there's
activity, scales with the deck resize, and stops at FULLY_DONE.

---

## A15 — Freeze Total time at FULLY_DONE

**Target:** Web `#live-total-time` update logic and the TUI total-time rendering
(also item B3).

**Requirement:** When the run reaches `FULLY_DONE`, **stop** the Total timer so its
final value is preserved afterwards (instead of continuing to tick after the run
has stopped, which currently makes "how long it took" unknowable later).

**Implementation recipe (web):**
1. In the poll/update loop, detect `run.action_status === 'FULLY_DONE'` (or the
   terminal-status flag from `completion_callback.get_run_terminal_status`).
2. On first detection, cache the final total: `frozenTotal = computeTotal(now)`,
   and set a `runDone = true` flag.
3. While `runDone`, always write the cached `frozenTotal` to `#live-total-time`
   and stop recomputing from wall-clock. Also stop the braille-snake loader (A14)
   and optionally turn the timer green.
4. Keep the value in MM:SS (extending to HH:MM:SS if ≥ 1h, matching the chosen
   formatter). Ensure Agent time can also freeze at the same moment.
5. `completion_callback.py` already exposes terminal detection; reuse its semantics
   (`final_verdict.FULLY_DONE`, status `FULLY_DONE`, or terminal events) so the web
   and callback logic agree on the exact completion event.

**Acceptance:** After FULLY_DONE the Total time is frozen at the true final duration;
leaving the page open for minutes no longer inflates the "how long it took" reading.

---

# PART B — TUI UPGRADES (3 items)

---

## B1 — `P: XX%` → `Progress: XX%`, same progress as web

**Target:** `qq-tui/src/widgets/status_bar.rs` — `build_builtin_bar()` center segment,
and the color-paint prefix table in `paint_colored_segments()`.

**Requirement:** Change the TUI progress indicator from `P≈XX%` (or `P: XX%`) to
`Progress: XX%`, and make the **numeric value update identically** to the web
`PROGRESS` meter (same `effective_progress_pct` source, same clamp 0–100, same
rounding).

**Implementation recipe:**
1. In `build_builtin_bar()`, replace the center format fragment:
   - Current: `"P{approx}{pct}%"` (where `approx` is `≈` from `t.approx()`).
   - New: `"Progress: {pct}%"`.
2. Update the `paint_colored_segments()` prefix matcher that currently colors
   `"P\u{2248}"` (the `P≈` token); change it to color `"Progress:"` (or the whole
   `Progress: NN%` via the same numeric-coloring pass) using `t.color_progress_value()`.
3. Value parity: confirm the TUI `progress` field is driven by the **same**
   `effective_progress_pct` (from `qq/progress.py`) that the web meter uses, and
   both clamp to `0.0..=100.0` and truncate to integer percent the same way
   (`pct as u64`). If the TUI currently sources progress from a different signal,
   unify them so B1's numbers exactly match A3's web numbers tick-for-tick.
4. Watch for the `Center:`/`Center` coloring logic that also keys on `"Progress:"`
   vs the old `"P≈"` — ensure no stale prefix remains.

**Acceptance:** TUI center reads `Progress: 37%` and mirrors web `PROGRESS: 37%`
at every poll.

---

## B2 — `Cyc=1/∞` → `Cycle=1/∞`, bump on review→build handoff

**Target:** `qq-tui/src/widgets/status_bar.rs` — center segment
`"Cyc={cycle}/{max_display}"`, and the cycle-increment call site in `app.rs` /
backend handoff logic.

**Requirement:** Rename `Cyc=` → `Cycle=`, keep the `1/∞` form, and bump the left
number `+1` **only** when inspeQtor hands the reviewed output back to construQtor.

**Implementation recipe:**
1. In `build_builtin_bar()`, change `"Cyc="` → `"Cycle="`. Keep
   `max_display` = `"∞"` when `max_cycles == 0`, else the number (existing logic).
2. Update `paint_colored_segments()` prefix list: the current entry
   `("Cyc=", t.color_cycle_value())` becomes `("Cycle=", t.color_cycle_value())`.
3. Locate where `self.status.cycle` is incremented (call to `increment_cycle()` /
   `self.status.cycle += 1` / an event handler mapping the inspeQtor→construQtor
   handoff). Ensure the trigger is the **review-completed → builder-resume** handoff
   exactly (an event like `review.done` / `handoff` / `construqtor` receiving
   reviewed output), not a generic status change. If it currently increments
   elsewhere, move it to the inspeQtor-returns-to-construQtor transition.
4. Confirm the same increment semantics are shared with the web A12 change so both
   UIs show identical cycle numbers.

**Acceptance:** TUI shows `Cycle=1/∞` (or `Cycle=2/∞` after one handoff), increments
by exactly one per constructor-resume-after-review.

---

## B3 — Freeze Total time at FULLY_DONE (TUI)

**Target:** `qq-tui/src/status.rs` (time methods) and `status_bar.rs`
(`build_builtin_bar()` `Total={total}`), plus the terminal-state detection hook in
`app.rs`.

**Requirement:** Stop the Total timer at FULLY_DONE so the final duration is
preserved, matching web A15.

**Implementation recipe:**
1. Add a frozen-total concept to `StatusState`, e.g.:
   ```rust
   pub frozen_total: Option<Duration>,   // set once at terminal
   pub terminal_reached: bool,
   ```
2. In `total_elapsed_secs()` (or a new `display_total_secs()`), return the frozen
   value when `frozen_total` is `Some(t)` instead of `Utc::now() - session_started_at`.
3. In `app.rs`, detect the FULLY_DONE terminal state (inspect the event stream /
   parsed status for `FULLY_DONE`, or call the equivalent of
   `get_run_terminal_status` semantics). On first detection:
   - `self.status.frozen_total = Some(self.status.total_elapsed());`
   - `self.status.terminal_reached = true;`
   - `self.status.stop_active();` (freeze Agent time too).
4. `build_builtin_bar()` continues to use `status::fmt_elapsed(self.state.total_elapsed_secs())`
   for `Total=`, so the frozen value renders automatically. Optionally paint the
   frozen total green when `terminal_reached`.
5. Keep the rest of the bar live (spinner stops is fine; cycle/progress/action may
   freeze naturally). Do not freeze the whole render loop — only the time value.

**Acceptance:** After FULLY_DONE, TUI `Total=` stays fixed at the true elapsed time
indefinitely; the value matches web A15 for the same run.

---

# CROSS-CUTTING CONSISTENCY CHECKS (apply after everything)

1. **Progress parity (A3 ↔ B1).** Web `PROGRESS: X%` and TUI `Progress: X%` must
   show the same integer at the same moment (same backend source, same clamp, same
   truncation).

2. **Cycle parity (A12 ↔ B2).** Web `Cycle=N/∞` and TUI `Cycle=N/∞` show the same
   `N`; both increment only on the inspeQtor→construQtor review handoff.

3. **Total-time parity (A15 ↔ B3).** Web `Total: MM:SS` and TUI `Total=MM:SS` freeze
   to the same value at the same FULLY_DONE moment.

4. **Model parity (A13).** Web `[fla]` and TUI `[fla]` use the same abbreviation map
   (`fla`, `fla-T`, `pro`, `pro-T`).

5. **Agent colors (A6) ↔ TUI palette.** Web per-agent terminal colors (cyan/pink/
   yellow/green on black) should visually match the TUI's agent role coloring if any,
   so a user moving between UIs sees the same agent identity.

6. **Action bar parity (A2 ↔ TUI right segment).** Web `Act:X` (A2) and TUI
   `Act:{action}` (right segment) should show the same action label at the same time.

---

# VERIFICATION CHECKLIST

After implementing, run and confirm:

```bash
# Backend / Python tests
cd /Users/wicked/x/qonqrete
source .venv/bin/activate
python3 -m pytest tests/ -q

# Build the Rust TUI (validates status_bar.rs compile after text edits)
cd /Users/wicked/x/qonqrete/qq-tui
cargo build --release

# Full end-to-end smoke
cd /Users/wicked/x/qonqrete
python3 -m qq run qq/../task.md /some/target
```

**Manual UI checks (web):**
- [ ] Top menu shows **BOARD** and **RUNS** (A1).
- [ ] Top-right shows **Act:Planning/…** and no CONNECTED bars (A2).
- [ ] Top-right progress reads **PROGRESS: NN%** (A3).
- [ ] The duplicate `panel-view-label` is gone; only the yellow tab is active (A4).
- [ ] Click an agent terminal → full-screen overlay tails only that agent; ✕ closes (A5).
- [ ] Four agent terminals: cyan / pink / yellow / green on black (A6).
- [ ] Tasks page has no Build Groups (A7).
- [ ] Tasks page 50/50 split, two scrollbars, click-to-focus (A8).
- [ ] Config page background near-black and readable (A9).
- [ ] **Total:** and **Agent:** blocks next to PROGRESS tick live (A10).
- [ ] Version number under the squid scales with deck resize (A11).
- [ ] Top bar shows **Cycle=1/∞**, increments on review→build handoff (A12).
- [ ] Top bar model reads `[fla]`-style abbreviation (A13).
- [ ] Braille-snake animates above squid, scales, stops at FULLY_DONE (A14).
- [ ] Total time freezes at FULLY_DONE (A15).

**Manual UI checks (TUI):**
- [ ] Center reads **Progress: NN%** and matches web (B1).
- [ ] Center reads **Cycle=N/∞** and increments on handoff (B2).
- [ ] **Total=** freezes at FULLY_DONE (B3).

---

## REVISIONS / SOURCE OF TRUTH

This document supersedes the prior `qq-ultimate-finish.md`. It is derived from
`../qq-web-tui-finish.md` and extended into precise, code-grounded instructions
against:

- `qq/web/api.py` (web frontend: HTML, CSS, JS)
- `qq/web/process.py` (dashboard lifecycle)
- `qq/progress.py` (progress source)
- `qq/completion_callback.py` (FULLY_DONE terminal detection)
- `qq/qontroller.py` (agent handoff / cycle increment)
- `qq-tui/src/status.rs` (StatusState time/cycle model)
- `qq-tui/src/widgets/status_bar.rs` (status bar render & coloring)
- `qq-tui/src/app.rs` (event loop / action status / terminal detection)
