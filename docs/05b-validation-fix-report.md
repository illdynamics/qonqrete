# Post-05B Fix Report

## What was fixed
- Clarified bridge runs no longer continue via `reqap -> next tasq` by default. In `qrane/qrane.py`, the bounded post-05 path now stops after the clarified pass unless legacy continuation is explicitly re-enabled. `qonqrete.sh` now exposes this as `--legacy-cycle-continuation`.
- VS Code and IntelliJ wrappers were moved onto the CLI’s task-file-first path instead of reinforcing hidden `tasq.md` copy/swap behavior on normal runs. The main run paths now pass task files directly.
- High-signal CLI/help/docs/plugin surfaces were tightened to reduce `tasq.md` / `sqrapyard` drift and to describe `sqrapyard` as legacy compatibility, not the main story.
- Top-level docs/plugin READMEs now add explicit validation-reality language: deterministic validation is strongest for Python and weaker outside Python.

## 05A blocker status
### Fully resolved in-scope
- `Legacy reqap -> next tasq continuation is still active runtime behavior underneath`
  - It is no longer the default clarified bridge behavior. It is now explicit compatibility mode.

### Partially improved
- `No end-to-end live model-backed run was proven`
  - I added a stronger real runtime smoke through `qrane.py` with actual Qrystallizer/Guard execution and bounded-stop behavior, but this was still not a live model-backed full build.
- `Documentation and IDE/plugin surfaces still show noticeable tasq.md / sqrapyard drift`
  - Major CLI/README/QUICKSTART/VS Code/IntelliJ surfaces were cleaned up, but historical repo drift still exists outside the focused bridge path.
- `Deterministic validation remains Python-strong and non-Python-weaker`
  - Overclaim/drift was reduced in the most visible docs/surfaces, but the underlying capability asymmetry still exists.

### Still unresolved
- `pytest-based validation could not run`
  - Fresh retry still fails because `pytest` is not installed.

## Validation commands run
```text
bash -n qonqrete.sh
python3 -m py_compile qrane/qrane.py
python3 -m json.tool vscode-extension/package.json >/dev/null
./qonqrete.sh --help | sed -n '1,80p'
python3 - <<'PY' ... continuation harness for handle_cheqpoint/promote_reqap ... PY
python3 - <<'PY' ... wrapper/doc source checks ... PY
python3 - <<'PY' ... temp-workspace qrane runtime smoke (tasqleveler + guard) ... PY
python3 -m pytest -q intellij-plugin/src/test/kotlin/sh/qonqrete/intellij/QonQreteServiceTest.kt
```

## Validation results
- `bash -n`: passed
- `py_compile` for `qrane/qrane.py`: passed
- `package.json` JSON parse: passed
- CLI help check: passed; new compatibility flag is visible
- Continuation harness: passed
  - clarified bridge path returns bounded stop
  - legacy continuation still works only when explicitly enabled
- Wrapper/doc source checks: passed
- Real runtime smoke: passed
  - `qrane.py` executed against a temp workspace
  - `task/task-spec.v1.json` and `guard/guard-result.v1.json` were emitted
  - manifest reached `RUN_COMPLETED`
  - no implicit `cyqle2_tasq.md` was created
- `pytest`: failed immediately
  - `/Users/wicked/.asdf/installs/python/3.12.6/bin/python3: No module named pytest`

## What still waits for 06/07/08
- Full retirement of cycle-era continuation and related legacy artifacts
- Full repo-wide cleanup of remaining historical `tasq.md` / `sqrapyard` wording
- Broader non-Python deterministic validation
- Transaction/write hardening
- A true end-to-end live model-backed proof run

## Proceeding status
- The repo is now in a stronger and safer post-05 bridge state for proceeding to 06/07/08.
- The bridge is cleaner and more truthful than 05A, but it is still not honestly “fully demo-proven” until a real live model-backed full run is executed.
