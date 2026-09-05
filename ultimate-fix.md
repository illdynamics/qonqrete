The current failure is:

[codeseeq] runtime_mode=host cmd_arg=run
[codeseeq:error] host runtime requires local Codex CLI. Install it with: npm install -g @openai/codex@0.130.0

The target workspace remains empty except for .qq/.codeseeq metadata and .qq_prompt_call-*.md files. No index.html, CSS, JS, SVG, or image files are created. inspeQtor correctly reports NOT_DONE because construQtor failed before writing construqtor_output.json.

Root cause:
QonQrete invokes `codeseeq run`, but QonQrete currently forces CodeSeeq into host runtime mode from config/env. On top of that, the construQtor call is being wrapped by QonQrete’s own bubblewrap sandbox. This causes double isolation. CodeSeeq/Codex already has its own sandboxing behavior, and QonQrete’s extra bubblewrap layer hides host/runtime dependencies, writable paths, or bridge state from CodeSeeq. The result is that CodeSeeq fails before construQtor can write files or status JSON.

New design decision:
Do NOT wrap construQtor calls in QonQrete’s external bubblewrap sandbox.
Please REMOVE the bubblewrap sandbox that construQtor is being wrapped in now.
DO keep the bubblewrap installed, so dont remove it from any dependencies or whatsoever, only remove the actual sandboxing of our construQtor agent by it. 

construQtor must rely on CodeSeeq/Codex internal sandboxing only.

QonQrete may still pass the intended sandbox policy/mode to CodeSeeq, but QonQrete itself must not put construQtor inside an additional bubblewrap jail.

fix this and tell me exactly what you have done. do nothing more then this please.
