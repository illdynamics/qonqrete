Implemented the repair-plan continuation migration in `worqer/inspeqtor.py`, `qrane/qrane.py`, and `qrane/manifest_bridge.py`.

Added explicit `inspection-verdict.v1` repair semantics plus `repair-plan.v1` emission, manifest-linked repair/continuation artifacts, `RUN_REPAIR_PENDING` / `CONTINUABLE` / `REPAIRING` runtime handling, same-run targeted repair preparation from bounded briq scope, and explicit deferred `continuation-metadata.v1` for later linked runs. Canonical continuation now stops or routes through repair artifacts; `reqap -> next tasq` remains compatibility-only behind the legacy gate.

Validated with `python3 -m py_compile qrane/qrane.py qrane/manifest_bridge.py worqer/inspeqtor.py`.
