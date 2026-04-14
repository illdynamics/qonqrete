Implemented demo-ready separation in `worqer/inspeqtor.py` and `qrane/manifest_bridge.py`. Inspection no longer treats `exeq` summaries and reqaps as the sole evidence story. It now emits explicit `validation/validation-bundle.v1.json`, `realization/realization-bundle.v1.json`, `verdict/inspection-input.v1.json`, and `verdict/inspection-verdict.v1.json`, plus readable markdown summaries, and the manifest bridge links those real artifacts without overwriting them with thinner synthesized versions.

Validation / realization / inspection boundaries changed as follows. Validation now records deterministic guard results, Python-centric local verification, grouped/component coherence checks, capability disclosures, and explicit unknowns. Realization now records changed-file truth, touched scopes, undeclared scope drift, observed vs unverified behavior, evidence status, and confidence. Inspection now consumes validation + realization + completion criteria before verdict, judges criteria explicitly, and preserves deterministic failure as authoritative. Audit readability was improved by separating observed facts, inferred limits, and unresolved blind spots.

Validation commands run:
- `python3 -m py_compile worqer/inspeqtor.py qrane/manifest_bridge.py worqer/guard.py worqer/qrystallizer.py worqer/instruqtor.py worqer/construqtor.py worqer/loqal_verifier.py`
- `python3 -m py_compile worqer/inspeqtor.py qrane/manifest_bridge.py`
- `python3` smoke harness with stubbed `lib_ai` to generate validation/realization/verdict artifacts and confirm manifest linkage
- Attempted: `python3 -m pytest -q intellij-plugin/src/test/kotlin/sh/qonqrete/intellij/QonQreteServiceTest.kt`

Validation results:
- `py_compile`: passed
- Smoke harness: passed
  - grouped coherence `PASS`
  - validation bundle `PASS`
  - realization bundle `EVIDENCE_COMPLETE`
  - inspection input `READY`
  - inspection verdict `SUCCESS`
  - manifest linked validation, realization, inspection input, and inspection verdict artifacts correctly
- `pytest`: failed immediately because `pytest` is not installed in the environment

Evidence / capability disclosure behavior added:
- explicit validation execution mode
- explicit Python-strong / non-Python-weaker deterministic coverage disclosure
- explicit evidence status and confidence in realization + verdict
- explicit unknowns for missing test runner coverage, missing telemetry, and legacy direct-write recovery risk

Remaining blockers / intentionally deferred:
- no full executed project-wide test runner integration yet
- non-Python deterministic validation remains weaker than Python
- no deep Codex execution integration
- no full repair-plan migration
- no repo-native CLI migration
- no transaction hardening beyond honest legacy direct-write disclosure
