# QonQrete Results / Realization

## Purpose
The Results / Realization layer is the authoritative observed-outcome layer of QonQrete. Its job is to describe what actually changed, what actually happened, what behavior actually occurred, what impact was actually observed, what evidence exists for those claims, and what remains unknown.

This layer exists separately from planning because plan artifacts define intended outcomes, not actual outcomes.

This layer exists separately from validation because validators establish deterministic truth for the checks they directly perform, but do not by themselves compose the full observed-outcome picture of a run.

This layer exists separately from judgment because inspection decides what observed reality means, while realization only records that reality and its evidence.

This layer closes the loop between execution and autonomous control by ensuring the system observes reality before it is allowed to decide, repair, continue, or learn from that reality.

## Core Principle
Execution is not the same as outcome.

Validation is not the same as realization.

Realization is not the same as judgment.

The system must observe reality before it is allowed to decide what that reality means.

A build can complete without proving intended behavior.

A validator can pass specific checks without proving whole-system completion.

A realization record can show mixed, partial, or unknown outcomes without asserting success or failure.

Only after realization exists may inspection, repair targeting, continuation routing, or completion claims be made canonically.

## Position in the System
Canonical flow position:
- `intake -> clarification -> guard -> planning -> build -> validation -> realization -> inspection -> repair/continue/complete`

Relationship to `construQtor`:
- construQtor produces build outputs, changed-file manifests, scope application records, and build logs
- realization consumes build evidence but does not inherit construQtor’s authority
- realization must not treat build completion as proof of outcome

Relationship to deterministic validators:
- validators produce direct deterministic evidence for the checks they run
- realization composes validator results into scoped outcome records
- realization must not replace validators or reinterpret failed deterministic checks as passing

Relationship to Run Manifest:
- realization artifacts must be created before canonical inspection verdicts
- realization outputs must be linked in the Run Manifest as first-class stage artifacts
- realization stage status must be explicit in the manifest

Relationship to `inspeQtor`:
- inspeQtor consumes realization bundles as authoritative observed-outcome inputs
- inspeQtor must not infer closure from plan text or build output alone when realization exists

Relationship to repair flow:
- repair plans must reference realization artifacts to identify affected scopes, behaviors, and unknowns
- repair targeting depends on realization accuracy and scope clarity

Relationship to continuation flow:
- continuation decisions must use realization to determine what evidence exists, what remains unresolved, and what state is safe to continue from
- continuation metadata must reference realization artifacts when a run is extended

Relationship to future evolution / learning loops:
- future adaptive or learning systems may consume realization artifacts as observed-reality inputs
- realization is the only valid substrate for post-run learning because it distinguishes observed, inferred, and unknown claims

## Result / Realization Scope Model
### Structural Reality
Structural Reality records what actually changed in the artifact and code surface.

Minimum dimensions:
- changed files
- touched components
- dependency changes
- artifact creation, update, removal
- declared scope versus actual touched scope
- partial or uncommitted change evidence when available

Structural Reality must answer:
- which files changed
- which files were created or removed
- which planned scopes were touched
- whether undeclared scopes were touched
- whether dependency structures changed
- which artifacts were emitted

### Behavioral Reality
Behavioral Reality records what behavior was actually observed, not what behavior was intended.

Minimum dimensions:
- test outcomes
- runtime behavior changes
- interface behavior changes
- command or execution outcomes
- output deltas where measurable
- explicitly unverified behaviors

Behavioral Reality must answer:
- which behaviors were executed and observed
- which expected behaviors passed
- which behaviors failed
- which behaviors changed unintentionally
- which behaviors remain unverified

### System Impact Reality
System Impact Reality records system-level impact where evidence exists.

Minimum dimensions:
- performance changes
- error-rate changes
- stability signals
- resource-impact signals
- environment-specific impact notes
- explicit absence of impact evidence

System Impact Reality must answer:
- whether measurable system-level impact evidence exists
- whether performance, memory, or stability changed
- whether error signals changed
- whether environment limits prevent reliable interpretation

### Confidence / Evidence Reality
Confidence / Evidence Reality records what kind of evidence exists for the above claims.

Minimum dimensions:
- directly observed facts
- indirectly inferred claims
- unknowns
- missing evidence
- capability-mode limitations
- evidence completeness status

Confidence / Evidence Reality must answer:
- what was directly observed
- what was inferred from partial evidence
- what remains unknown
- how evidence depth limits confidence

## Separation of Concerns
### Plan
May claim:
- what should be built
- what completion criteria should be checked
- what validation should run
- what scopes are intended

May not claim:
- what actually changed
- what actually happened at runtime
- that intended behavior is confirmed
- that completion is achieved

### Execution
May claim:
- what actions were attempted
- what files were written or targeted
- what commands were run
- what build groups were applied

May not claim:
- that behavior is correct
- that tests passed unless validator evidence exists
- that intended outcome was achieved
- that the system is complete

### Validation
May claim:
- what checks were directly performed
- whether those checks passed, failed, or were skipped
- deterministic truth for its implemented checks
- validation coverage limitations

May not claim:
- complete observed system reality by itself
- business completion by itself
- final success or failure of the run by itself
- intent-versus-outcome judgment by itself

### Realization
May claim:
- what structural changes were observed
- what behavioral outcomes were observed
- what system impacts were observed where evidence exists
- what evidence supports those claims
- what remains inferred or unknown

May not claim:
- that the plan was good
- that the run is successful or complete
- that repair is required
- that architectural correctness is proven unless evidence directly supports it

### Inspection Verdict
May claim:
- whether observed reality satisfies completion criteria
- whether repair is required
- confidence in correctness
- unresolved issues and next actions

May not claim:
- raw observational facts that are absent from realization
- deterministic truths that validators did not establish
- hidden rationale not linked to evidence

### Repair Planning
May claim:
- what scope should be repaired
- what evidence triggered repair targeting
- what follow-up validation is required

May not claim:
- that repair succeeded before execution
- that a broader scope change is allowed without explicit basis
- that unknowns do not matter when realization says otherwise

## Required Inputs to Realization
Realization requires, at minimum:
- Build Reports
- changed-file manifests
- validator outputs
- test outputs
- execution logs where allowed
- manifest references
- scoped runtime evidence
- completion criteria references
- capability mode and validation execution mode
- build-scope identifiers
- dependency and component references where relevant

Optional but supported inputs:
- runtime startup logs
- benchmark outputs
- resource usage summaries
- interface snapshots
- deployment or environment probes where allowed

## Required Outputs from Realization
Realization must emit:
- Result / Realization Bundle
- changed-scope summary
- behavioral delta summary
- system-impact summary
- evidence references
- unknowns / blind spots disclosure
- realization confidence / evidence status
- direct versus inferred claim separation
- scope linkage to build groups, validators, and manifest

## Realization Rules
- realization must describe observed reality, not desired reality
- realization must not silently upgrade inferred claims into observed facts
- realization must distinguish:
  - observed
  - inferred
  - unknown
- realization must preserve scoped evidence links
- realization must be compatible with bounded repair targeting
- realization must lower confidence when execution or testing depth is limited
- realization must disclose capability-mode limitations honestly
- realization must exist before canonical inspection verdicts
- realization must remain separate from plan text, validator raw output, verdict text, and repair text
- realization must support both whole-run view and scope-level view
- realization must not suppress undeclared scope changes
- realization must not hide missing impact evidence behind neutral wording
- realization must remain attributable to a specific run and stage
- realization must remain attributable to specific build scopes where applicable

## Canonical Flow Relationship
Canonical flow:
- `intake -> clarification -> guard -> planning -> build -> validation -> realization -> inspection -> repair/continue/complete`

Why realization must exist before inspection verdicts:
- build only proves actions were attempted
- validation only proves the checks that ran
- realization composes those outputs into an observed-outcome record
- without realization, inspection would be forced to infer outcome from partial build and validation fragments
- realization prevents inspection from hallucinating closure from plan text, build logs, or isolated validator results
- realization gives repair targeting a scoped evidence membrane between execution and judgment

## Realization Ownership Model
Who produces raw evidence:
- construQtor produces build reports, changed-file manifests, build-group records, and execution logs
- System Validators produce deterministic validation bundles, test outputs, and coverage disclosures
- runtime or execution environment may produce command logs, scoped runtime evidence, and resource usage outputs where available

Who composes realization bundles:
- the Result / Realization layer composes canonical realization artifacts from raw evidence
- this may be implemented as a dedicated realization stage or compatibility wrapper during migration
- composition authority belongs to realization, not to build or inspection

Who consumes realization bundles:
- inspeQtor
- repair flow
- continuation flow
- Run Manifest
- future learning or adaptive layers
- human audit consumers

Who may reference but not mutate realization records:
- construQtor
- validators
- Runtime / Orchestrator after creation except for manifest linkage
- downstream audit/reporting systems
- continuation and repair routing logic

## Result / Realization Bundle Contract
Required fields:
- `schema_version`
- `realization_bundle_id`
- `run_id`
- `stage`
- `status`
- `capability_mode`
- `validation_execution_mode`
- `evidence_status`
- `confidence`
- `scope_summary`
- `structural_reality`
- `behavioral_reality`
- `system_impact_reality`
- `unknowns`
- `evidence_refs`
- `source_build_refs`
- `source_validation_refs`
- `manifest_ref`
- `created_at`

Ownership:
- Result / Realization layer

Linkage rules:
- must be linked from Run Manifest
- must reference the build reports and validation bundles it composes
- must be attributable to the canonical `REALIZATION` stage
- must remain stable after creation except for explicit versioned supersession

Scope rules:
- must record both intended scope reference and actual touched scope
- must record undeclared touched scope if observed
- must be decomposable by build group, component group, or run summary

Confidence rules:
- confidence is a property of evidence depth, not of optimism
- weaker execution or validation modes must reduce confidence
- unknowns and missing evidence must reduce confidence
- direct deterministic and direct execution evidence increase confidence

Schema versioning requirements:
- must include `schema_version`
- canonical version label should begin with `realization-bundle.v1`

Concrete JSON schema example:
```json
{
  "schema_version": "realization-bundle.v1",
  "realization_bundle_id": "realization-001",
  "run_id": "run-001",
  "stage": "REALIZATION",
  "status": "EVIDENCE_PARTIAL",
  "capability_mode": "MIXED_REASONING_EXECUTION",
  "validation_execution_mode": "STATIC_ONLY",
  "evidence_status": "EVIDENCE_PARTIAL",
  "confidence": "CONFIDENCE_MEDIUM",
  "scope_summary": {
    "intended_scopes": ["component-group:auth-service"],
    "touched_scopes": ["component-group:auth-service"],
    "undeclared_touched_scopes": []
  },
  "structural_reality": {
    "changed_files": [
      {
        "path": "src/auth/service.py",
        "change_type": "modified",
        "evidence_class": "direct_execution_evidence"
      },
      {
        "path": "src/auth/tokens.py",
        "change_type": "created",
        "evidence_class": "direct_execution_evidence"
      }
    ],
    "touched_components": ["auth-service"],
    "dependency_changes": [
      {
        "type": "module_usage_change",
        "summary": "auth-service now depends on token helper module",
        "evidence_class": "indirect_inferred_evidence"
      }
    ],
    "artifact_changes": [
      {
        "artifact_type": "build_report",
        "path": ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json"
      }
    ]
  },
  "behavioral_reality": {
    "observed_behaviors": [
      {
        "behavior_id": "python-syntax-parse",
        "result": "passed",
        "evidence_class": "direct_deterministic_evidence"
      }
    ],
    "failed_behaviors": [],
    "unverified_behaviors": [
      {
        "behavior_id": "integration-tests",
        "reason": "not executed in current validation mode"
      }
    ],
    "interface_behavior_deltas": []
  },
  "system_impact_reality": {
    "performance": {
      "status": "unknown",
      "reason": "no benchmark or runtime measurement executed"
    },
    "stability": {
      "status": "unknown",
      "reason": "no long-running execution evidence available"
    },
    "resource_usage": {
      "status": "unknown",
      "reason": "no resource telemetry collected"
    },
    "error_signals": []
  },
  "unknowns": [
    "Runtime startup behavior remains unverified",
    "Integration correctness remains unverified"
  ],
  "evidence_refs": [
    ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json",
    ".qonqrete/runs/run-001/build/groups/bg-auth/changed-files.v1.json",
    ".qonqrete/runs/run-001/validation/validation-bundle.v1.json"
  ],
  "source_build_refs": [
    ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json"
  ],
  "source_validation_refs": [
    ".qonqrete/runs/run-001/validation/validation-bundle.v1.json"
  ],
  "manifest_ref": ".qonqrete/runs/run-001/run-manifest.v1.json",
  "created_at": "2026-04-10T14:38:12Z"
}
```

## Changed Scope / Changed File Evidence Model
Changed-file manifests must record:
- file path
- change type: created, modified, deleted, attempted, unknown
- scope ID
- build group ID
- whether file was in intended scope
- whether change is committed, partial, or uncertain when supported
- evidence class
- source build report reference

Touched component manifests must record:
- component ID
- scope ID
- touched files
- dependency links affected
- whether touch was declared or undeclared

Dependency impact references must record:
- dependency edge changed or suspected changed
- evidence source
- whether impact is direct or inferred

Relationship to scoped builds and rollback/recovery:
- every changed-file record must be attributable to a scoped build
- if rollback exists, changed-file evidence must record rollback status
- if rollback does not exist, changed-file evidence must record recovery risk or partial-write exposure
- realization uses changed-scope evidence as the structural truth basis for repair targeting

Concrete example:
```json
{
  "schema_version": "changed-scope-manifest.v1",
  "changed_scope_manifest_id": "changed-scope-001",
  "run_id": "run-001",
  "build_group_id": "bg-auth",
  "scope_id": "scope_build_group_auth",
  "component_refs": [
    {
      "component_id": "auth-service",
      "touched_files": [
        "src/auth/service.py",
        "src/auth/tokens.py"
      ],
      "declared_touch": true
    }
  ],
  "changed_files": [
    {
      "path": "src/auth/service.py",
      "change_type": "modified",
      "in_intended_scope": true,
      "commit_state": "applied",
      "evidence_class": "direct_execution_evidence",
      "source_build_ref": ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json"
    },
    {
      "path": "src/auth/tokens.py",
      "change_type": "created",
      "in_intended_scope": true,
      "commit_state": "applied",
      "evidence_class": "direct_execution_evidence",
      "source_build_ref": ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json"
    }
  ],
  "dependency_impacts": [
    {
      "from_component": "auth-service",
      "to_component": "token-helper",
      "impact_type": "new_internal_dependency",
      "evidence_class": "indirect_inferred_evidence"
    }
  ],
  "rollback_recovery_state": {
    "write_strategy": "direct_with_recovery_risk",
    "rollback_available": false
  }
}
```

## Behavioral Delta Model
Behavioral Delta records:
- what behavior was expected
- what behavior was observed
- where behavior changed as intended
- where behavior changed unintentionally
- what remains unverified

Behavioral Delta contract rules:
- expected behavior comes from plan references, not from realization invention
- observed behavior must cite evidence
- unintended behavior must not be hidden because the overall build “looks good”
- unverified behavior must remain explicit

Concrete example:
```json
{
  "schema_version": "behavioral-delta.v1",
  "behavioral_delta_id": "behavior-001",
  "run_id": "run-001",
  "expected_behaviors": [
    {
      "behavior_id": "auth-login-success",
      "source_ref": ".qonqrete/runs/run-001/planning/completion-criteria.v1.json",
      "description": "Login returns token for valid credentials"
    },
    {
      "behavior_id": "auth-login-invalid-fails",
      "source_ref": ".qonqrete/runs/run-001/planning/validation-plan.v1.json",
      "description": "Invalid credentials are rejected"
    }
  ],
  "observed_behaviors": [
    {
      "behavior_id": "python-syntax-parse",
      "result": "passed",
      "evidence_class": "direct_deterministic_evidence",
      "evidence_ref": ".qonqrete/runs/run-001/validation/validation-bundle.v1.json"
    }
  ],
  "intended_behavior_changes_observed": [],
  "unintended_behavior_changes_observed": [],
  "unverified_behaviors": [
    {
      "behavior_id": "auth-login-success",
      "reason": "no executed behavioral test evidence"
    },
    {
      "behavior_id": "auth-login-invalid-fails",
      "reason": "no executed behavioral test evidence"
    }
  ]
}
```

## System Impact Model
System Impact records impact where evidence exists. It must not assume impact data is always available.

Impact dimensions:
- performance
- memory/resource usage
- stability indicators
- error signals
- environment-specific caveats

Representation rules:
- if evidence exists, record metric, direction, confidence, and evidence reference
- if evidence does not exist, explicitly record `unknown` with reason
- environment constraints must be included where they limit interpretation

Concrete example:
```json
{
  "schema_version": "system-impact.v1",
  "system_impact_id": "impact-001",
  "run_id": "run-001",
  "performance": {
    "status": "unknown",
    "reason": "no benchmark evidence collected"
  },
  "memory_resource_usage": {
    "status": "unknown",
    "reason": "no telemetry captured"
  },
  "stability_indicators": {
    "status": "unknown",
    "reason": "no repeated runtime execution available"
  },
  "error_signals": {
    "status": "observed",
    "items": []
  },
  "environment_caveats": [
    "Validation executed in static-only mode",
    "No runtime execution environment was used for impact measurement"
  ]
}
```

## Evidence Classification Model
Minimum evidence classes:
- direct deterministic evidence
- direct execution evidence
- indirect inferred evidence
- missing evidence

### Direct deterministic evidence
Definition:
- evidence produced by deterministic validators for checks they directly performed

Examples:
- syntax parsing result
- AST contract enforcement result
- linter result
- compile result

Downstream effect:
- strongest evidence for the specific check performed
- increases confidence for that narrow claim
- does not prove broader behavior beyond the direct check

### Direct execution evidence
Definition:
- evidence produced by actual execution, command outcomes, test runs, runtime probes, or other direct system interaction

Examples:
- test execution result
- process exit code
- startup log showing service booted
- benchmark output

Downstream effect:
- strongest evidence for behavioral and impact claims within the executed scope
- improves repair targeting precision
- materially strengthens final verdict confidence

### Indirect inferred evidence
Definition:
- a claim derived from observed structure or limited evidence rather than directly executed or deterministically proven fact

Examples:
- inferred dependency impact from changed imports
- inferred interface change from generated file shape
- inferred likely behavioral change from code delta

Downstream effect:
- must lower confidence relative to direct evidence
- may support suspicion, targeting, or caution
- must never be silently rephrased as confirmed observation

### Missing evidence
Definition:
- no evidence available for the claim or required observation

Examples:
- no runtime execution
- no test coverage for behavior
- no telemetry for performance impact

Downstream effect:
- lowers confidence
- weakens completion claims
- reduces repair precision
- must remain explicit in realization and inspection

## Relationship to Validators
- validators establish deterministic truth for what they directly verify
- realization composes validator results into scoped observed-outcome records
- realization must not replace validators
- validators must not be treated as the entire realization layer
- realization may summarize validator outputs in scope context, but must preserve direct references and coverage disclosures
- validator absence is not neutral; it becomes a realization unknown or missing-evidence condition

## Relationship to inspeQtor
- inspeQtor consumes realization, not just build output or plan text
- inspeQtor must use realization to determine:
  - completion
  - correctness confidence
  - repair targeting
  - unresolved unknowns
- realization must make blind spots explicit so inspeQtor cannot hallucinate closure
- realization must provide the evidence membrane that prevents inspection from treating “implemented files exist” as “behavior is proven”
- inspeQtor may interpret realization, but may not overwrite the underlying observed-outcome record

## Relationship to Repair Plans
Realization feeds repair targeting by exposing:
- affected components
- affected files
- failed behaviors
- uncertain behaviors
- evidence references
- missing evidence zones
- undeclared touched scope
- write-strategy and rollback exposure where relevant

Repair plans must reference realization artifacts:
- as evidence basis for scope targeting
- as evidence basis for uncertain behavior follow-up
- as evidence basis for selecting revalidation requirements
- as evidence basis for continuation safety

A repair plan that does not reference realization artifacts is structurally incomplete.

## Relationship to Run Manifest
When realization artifacts are created:
- after validation bundle creation
- before canonical inspection verdict
- once build, changed-scope, and validation evidence for the current scope are available

How they are linked in the Run Manifest:
- as canonical artifacts for the `REALIZATION` stage
- with timestamps, status, evidence status, and source references
- with links to changed-scope summaries and supporting scope artifacts

Stage linkage expectations:
- `REALIZATION` must appear as a distinct stage in canonical flow
- manifest must record stage start and completion
- inspection must not be marked complete before realization is present

Artifact linkage expectations:
- Run Manifest must link:
  - Result / Realization Bundle
  - changed-scope manifest
  - behavioral delta artifact
  - system impact artifact where available
  - source build reports
  - source validation bundles

How realization supports continuation and final completion evidence:
- continuation may reference realization to identify unresolved unknowns and safe resume points
- final completion claims must reference realization plus inspection, not inspection alone

Concrete manifest linkage example:
```json
{
  "schema_version": "run-manifest.v1",
  "run_id": "run-001",
  "stage": "REALIZATION",
  "lifecycle_status": "REALIZING",
  "run_status": "RUN_ACTIVE",
  "artifacts": {
    "build_output": ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json",
    "validation_output": ".qonqrete/runs/run-001/validation/validation-bundle.v1.json",
    "realization_output": ".qonqrete/runs/run-001/realization/realization-bundle.v1.json",
    "changed_scope_summary": ".qonqrete/runs/run-001/realization/changed-scope-manifest.v1.json",
    "behavioral_delta_summary": ".qonqrete/runs/run-001/realization/behavioral-delta.v1.json",
    "system_impact_summary": ".qonqrete/runs/run-001/realization/system-impact.v1.json"
  },
  "stages": [
    {
      "stage_id": "REALIZATION",
      "status": "completed",
      "started_at": "2026-04-10T14:38:00Z",
      "ended_at": "2026-04-10T14:38:12Z",
      "artifacts": [
        ".qonqrete/runs/run-001/realization/realization-bundle.v1.json",
        ".qonqrete/runs/run-001/realization/changed-scope-manifest.v1.json"
      ],
      "evidence_status": "EVIDENCE_PARTIAL"
    }
  ]
}
```

## Capability Mode / Ecosystem Disclosure
Realization must remain honest across:
- full execution plus tests
- partial execution
- syntax-only validation
- ecosystem-specific limits

### Full execution plus tests
Realization may claim:
- direct execution evidence for tested behavior
- higher confidence for observed behavior within executed scope
- stronger repair targeting precision

### Partial execution
Realization must:
- identify exactly which behaviors or scopes were executed
- identify which behaviors remain unverified
- lower confidence accordingly

### Syntax-only validation
Realization must:
- clearly state that behavior was not directly observed
- treat behavioral and system impact claims as unknown unless other evidence exists
- avoid “works” language

### Ecosystem-specific limits
Realization must:
- disclose language-specific strength and weakness
- record when deterministic validation is stronger in Python-centric flows
- record when other ecosystems received weaker or heuristic-only coverage
- lower confidence and verdict strength accordingly

Effects of weaker evidence modes:
- confidence decreases
- completion claims must narrow
- repair targeting becomes less precise
- final verdicts must remain cautious
- unknowns expand, not contract

## Audit / Transparency Requirements
- realization must support both human-readable and machine-readable views
- realization must be skimmable at high level and drillable at deep level
- realization must show:
  - what changed
  - why it matters
  - what evidence supports it
  - what is still unknown
- realization summaries must remain scoped and evidence-linked
- human-readable realization must not collapse direct, inferred, and unknown claims into one narrative blob
- machine-readable realization must remain sufficient for automated inspection and repair targeting
- audit consumers must be able to trace every material realization claim back to build, validator, or execution evidence

## Realization Anti-Patterns
Forbidden:
- treating build completion as success
- treating plan conformance as proof of behavior
- mixing verdict text into realization bundles
- hiding missing evidence
- collapsing unknowns into success language
- skipping realization when validators ran
- silently upgrading inferred claims into observed facts
- using plan text as substitute for observed behavior
- using validator outputs alone as full reality record
- omitting undeclared touched scope from realization
- hiding capability-mode weakness in realization summaries
- allowing realization artifacts to be overwritten by verdict summaries

## Migration / Compatibility Notes
- realization must bridge current fragmented logs into structured artifacts during migration
- legacy outputs such as `exeq.d/cyqleN_summary.md`, `cyqleN_changed.md`, per-briq exeQ files, validator outputs, and qage logs may be wrapped into canonical realization artifacts
- during migration, realization may be composed from:
  - Build Reports or legacy exeQ summaries
  - changed-file manifests
  - validator outputs
  - qage-local logs
  - manifest-linked compatibility references
- transitional realization is acceptable if:
  - it remains explicitly marked as compatibility-composed
  - it still distinguishes observed, inferred, and unknown
  - it still links supporting evidence
- final realization should be emitted as a native canonical stage artifact under `.qonqrete/realization/`
- compatibility wrapping must not silently claim that legacy outputs already satisfy the final native realization model

## Completion Criteria for This Layer
The Results / Realization layer can be considered properly implemented only when all of the following are true:
- canonical flow contains a distinct `REALIZATION` stage
- every canonical run emits a Result / Realization Bundle before inspection
- every realization bundle links build and validation evidence explicitly
- realization distinguishes structural, behavioral, system impact, and evidence reality
- realization distinguishes observed, inferred, and unknown claims
- changed-scope and changed-file truth is preserved in machine-readable form
- weaker capability modes reduce confidence and are disclosed explicitly
- inspection consumes realization rather than bypassing it
- repair plans reference realization artifacts
- Run Manifest links realization artifacts as first-class stage outputs
- human-readable realization summary and machine-readable realization bundle both exist
- legacy compatibility composition, if still used, is explicitly marked and evidence-linked
- completion claims cannot be made canonically without realization

## Inconsistencies or Open Risks
- current repo reality has no native canonical realization stage; observed-outcome evidence is fragmented across `exeq.d`, validator outputs, logs, and review artifacts
- current `construQtor` writes changed-file summaries, but those are not yet a full realization bundle
- current `inspeQtor` still performs review in a way that can mix evidence collection and judgment
- current pipeline ordering and docs disagree, which risks realization being bypassed or misrepresented if stage identity is not formalized
- current validation is Python-strong and broader ecosystem-weaker, which constrains realization confidence quality outside those stronger paths
- current build writes are non-transactional, so structural reality may include partial mixed state unless explicit recovery metadata is added
- current runtime lacks a canonical run manifest, so realization linkage is still structurally weaker until manifest adoption is complete
- current helper artifacts such as `qontext`, `bloq`, and cache outputs are not yet cleanly categorized as supporting evidence versus authoritative reality inputs
