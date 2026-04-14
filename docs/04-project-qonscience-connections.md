# QonQrete Qonscience

## Purpose of Qonscience
Qonscience is the authoritative contract layer for QonQrete. It defines how system parts relate, what each part owns, which artifacts are canonical, how authority is separated, how data moves, and where enforcement boundaries exist.

Qonscience exists to:
- define the authoritative contract layer governing all system interactions, artifacts, and responsibilities
- ensure all agents and system components operate within explicit, enforceable boundaries
- eliminate ambiguity in data flow, ownership, and execution authority
- provide one structural truth that runtime, manifests, validators, planning artifacts, and judgment artifacts can share
- prevent drift between current implementation reality, target architecture, migration bridge logic, and hard-rule constraints

Qonscience is not an execution plan, not a migration guide, and not a ruleset rewrite. It is the complete structural and behavioral connection model of the system.

## System Relationship Model
The canonical target relationship model is:

1. Qrystallizer defines readiness and structured task input.
2. Guard validates policy compliance and emits effective constraints.
3. instruQtor defines execution blueprint, component structure, dependency wiring, validation plan, and completion criteria.
4. construQtor builds scoped components and build groups within explicit contracts.
5. System Validators perform deterministic validation and executed verification where available.
6. Result / Realization records observed execution reality.
7. inspeQtor determines correctness, completion, and repair need from evidence.
8. Runtime / Orchestrator governs lifecycle, sequencing, stage gating, repair caps, and state updates.
9. Run Manifest acts as the single source of truth for run trace and artifact linkage.
10. Continuation metadata and repair plans govern any bounded follow-up execution.

Canonical authority separation:
- Qrystallizer owns clarification authority
- Guard owns pre-plan constraint authority
- instruQtor owns planning authority
- construQtor owns scoped build authority
- System Validators own deterministic correctness authority
- Result / Realization owns observed-outcome authority
- inspeQtor owns judgment authority
- Runtime / Orchestrator owns sequencing and lifecycle authority
- Run Manifest owns traceability authority

All status-bearing artifacts and runtime lifecycle states MUST align with the canonical stage/status/mode registry defined in the migration compound.

## Transition Boundary Notes
- `tasqleveler` exists only in current-state compatibility mode.
- Qrystallizer is the authoritative intake system in target state.
- qage/cycle execution is transitional, not canonical.
- `.qonqrete/` is the target canonical state root.
- manifest-based execution replaces fragmented logs as the authoritative linkage layer.
- bridge-flow behavior must not leak into final architecture as permanent canonical behavior.
- schema-versioned machine-readable artifacts are the canonical contract carriers during and after migration.
- `reqap -> next tasq` is compatibility-only continuation logic and is not canonical in Qonscience.
- current Python-centric validator strength remains real and must be disclosed until broader deterministic coverage exists.
- current repo reality still includes `tasqleveler`, cycle promotion, fragmented logging, and no canonical Qrystallizer implementation.

## Agent Contracts
### tasQleveler / Qrystallizer Transition Contract
Input:
- raw task input

Output:
- transitional structured task artifact or compatibility clarification residue
- replaced by canonical Qrystalized Task Spec

Responsibilities:
- compatibility-only task enhancement residue
- may assist migration from mutable task flow to structured clarification flow
- must preserve legacy evidence if invoked during transition

Must NOT:
- define final task schema
- remain the final intake authority
- mutate canonical clarified task once Task Spec exists
- ask questions mid-run after execution begins

Authority:
- compatibility-only clarification residue
- not canonical intake authority

Contract rule:
- if `tasqleveler` is used during transition, its output must be wrapped or converted into a canonical Task Spec before guard or planning begins

### Qrystallizer
Input:
- raw task input
- optional user clarifications
- optional default policy references and safe defaults

Output:
- Qrystalized Task Spec
- clarification log
- readiness state
- structured assumptions and unresolved unknowns

Responsibilities:
- gap detection
- bounded clarification questioning
- assumption capture
- readiness gating
- structured intake normalization

Must NOT:
- perform planning
- perform execution
- decide build grouping
- silently expand task scope
- ask questions after readiness is accepted and execution begins

Authority:
- clarification authority only

Contract rule:
- Qrystallizer is the only phase allowed to ask the user questions

### instruQtor
Input:
- Qrystalized Task Spec
- Guard Result
- effective constraints
- capability mode
- optional prior repair plan when planning reuse is allowed

Output:
- Execution Blueprint
- architecture foundation
- dependency and interaction contract
- component contracts
- validation plan
- completion criteria
- build grouping plan

Responsibilities:
- architecture definition
- component planning
- dependency mapping
- validation planning
- completion definition
- build scope structure

Must NOT:
- generate code
- perform deterministic validation execution
- silently alter clarification truth
- invent new user goals

Authority:
- planning authority only

Contract rule:
- planning outputs are canonical truth for build intent until explicitly superseded by a later planning artifact in a linked continuation

### construQtor
Input:
- Execution Blueprint
- component contracts
- build group scopes
- Guard Result / effective constraints
- capability mode
- Repair Plan when applicable

Output:
- code artifacts
- Build Reports
- changed-file manifests
- build logs
- scope application records

Responsibilities:
- implement scoped components
- follow contracts strictly
- operate within scoped build boundaries
- emit evidence of what it attempted and what it changed

Must NOT:
- change architecture
- skip required validation handoffs
- silently expand scope
- ask the user questions
- declare final correctness
- override planning authority
- rewrite component contracts without explicit planning-stage input

Authority:
- scoped build authority only

Contract rule:
- construQtor may only mutate declared build scope and must emit changed-file truth for every build group

### inspeQtor
Input:
- Build Reports
- Validation Bundles
- Result / Realization Bundles
- completion criteria
- Repair evidence where applicable
- capability disclosures

Output:
- Inspection Verdict
- Repair Plan when needed
- confidence classification
- unresolved issue list

Responsibilities:
- validate completeness from evidence
- detect issues
- determine repair targeting from evidence
- judge plan versus actual outcomes

Must NOT:
- perform execution
- ask user questions mid-run
- rewrite architecture
- replace deterministic validation authority
- invent missing realization evidence

Authority:
- judgment authority only

Contract rule:
- inspeQtor must consume realization and validation artifacts before issuing canonical verdicts

### System Validators (Non-AI)
Input:
- build outputs
- build scopes
- validation plan
- capability mode
- relevant ecosystem/tooling context

Output:
- Validation Result Bundle
- command results
- coverage disclosures
- deterministic issue records

Responsibilities:
- syntax validation
- execution validation
- test validation
- contract, policy, and mechanical checks where implemented
- grouped component coherence checks where supported
- capability coverage disclosure

Must NOT:
- judge business completion by themselves
- infer architectural correctness beyond their implemented checks
- ask user questions

Authority:
- final truth for deterministic correctness

Contract rule:
- deterministic validator results cannot be overridden by AI judgment

### Guard / Policy Validation Stage
Input:
- Qrystalized Task Spec
- default policy set
- configured policy overlays if present

Output:
- Guard Result
- effective constraints
- blocking issues
- warnings

Responsibilities:
- validate constraints
- block invalid tasks
- emit effective constraints for planning
- normalize policy enforcement inputs for downstream stages

Must NOT:
- perform planning
- perform code execution
- silently approve blocked policy violations

Authority:
- pre-plan constraint authority

### Runtime / Orchestrator
Input:
- canonical run configuration
- canonical stage registry
- manifest state
- stage outputs
- gating decisions

Output:
- lifecycle transitions
- stage execution control
- manifest updates
- continuation routing
- repair routing

Responsibilities:
- manage lifecycle
- enforce stage transitions
- update manifest
- enforce repair caps and continuation routing
- enforce no-mid-run-questioning rule
- enforce terminal-state integrity

Must NOT:
- invent undocumented statuses
- bypass required artifacts
- silently change capability mode
- silently remap stage authority

Authority:
- runtime control authority

## Data Contracts
All major machine-readable artifacts MUST:
- include `schema_version`
- include canonical status fields where applicable
- use canonical enums from the migration compound where applicable
- be linkable from the Run Manifest
- declare ownership and handoff semantics
- remain distinguishable from human-readable companion markdown

### Task Input Contract
Required fields:
- `schema_version`
- `task_input_id`
- `source_type`
- `source_ref`
- `content_ref` or `inline_content`
- `ingested_at`
- `run_id`
- `status`

Contract rules:
- raw intake artifact is immutable after ingestion
- raw intake is evidence, not clarified truth
- if the source is a file, the source reference must be preserved
- if the source is inline, the captured content must be persisted as an artifact

Ownership:
- Runtime / Orchestrator

Handoff semantics:
- handed from intake to Qrystallizer
- never consumed directly by build as canonical truth once Task Spec exists

Schema example:
```json
{
  "schema_version": "task-input.v1",
  "task_input_id": "task-input-001",
  "run_id": "run-001",
  "status": "RUN_CREATED",
  "source_type": "file",
  "source_ref": "./feature.md",
  "content_ref": ".qonqrete/runs/run-001/task/raw-input.md",
  "ingested_at": "2026-04-10T14:30:15Z"
}
```

### Qrystalized Task Spec Contract
Required fields:
- `schema_version`
- `task_spec_id`
- `run_id`
- `status`
- `goal`
- `inputs`
- `constraints`
- `assumptions`
- `blocking_gaps`
- `non_blocking_unknowns`
- `ready`
- `capability_mode`
- `clarification_summary`

Contract rules:
- `ready=true` is required before guard and planning
- blocking gaps must be empty when `ready=true`
- assumptions must be explicit and distinguishable from user facts
- no downstream stage may modify the canonical Task Spec in place
- later continuations may supersede it only through a new versioned artifact

Ownership:
- Qrystallizer

Handoff semantics:
- canonical clarification handoff from Qrystallizer to Guard and instruQtor

Schema example:
```json
{
  "schema_version": "task-spec.v1",
  "task_spec_id": "task-spec-001",
  "run_id": "run-001",
  "status": "READY_FOR_CLARIFICATION",
  "goal": "Implement authenticated API access for the repo service.",
  "inputs": [
    {
      "name": "task_file",
      "type": "markdown",
      "source_ref": "./feature.md"
    }
  ],
  "constraints": [
    "no network during validation by default",
    "preserve existing public auth route behavior unless changed explicitly"
  ],
  "assumptions": [
    {
      "assumption_id": "asm-001",
      "statement": "Use PostgreSQL as the default datastore",
      "basis": "No datastore specified"
    }
  ],
  "blocking_gaps": [],
  "non_blocking_unknowns": [
    "Token expiry duration may require later tuning"
  ],
  "ready": true,
  "capability_mode": "SIMULATION",
  "clarification_summary": "Task clarified with one default datastore assumption."
}
```

### Guard Result Contract
Required fields:
- `schema_version`
- `guard_result_id`
- `run_id`
- `status`
- `violations`
- `warnings`
- `effective_constraints`
- `policy_refs`
- `next_stage`

Contract rules:
- status must be one of `PASS`, `FAIL`, `REVIEW`
- `FAIL` blocks planning
- `effective_constraints` are canonical downstream constraints once emitted
- warnings must not be treated as hidden blockers

Ownership:
- Guard / Policy Validation Stage

Handoff semantics:
- handed from Guard to instruQtor and persisted in manifest
- later validation may reference the same constraints but must not redefine them silently

Schema example:
```json
{
  "schema_version": "guard-result.v1",
  "guard_result_id": "guard-001",
  "run_id": "run-001",
  "status": "PASS",
  "violations": [],
  "warnings": [],
  "effective_constraints": [
    "no architecture mutation during repair",
    "no scope expansion without replanning"
  ],
  "policy_refs": [
    "policy/defaults/security.v1.json"
  ],
  "next_stage": "PLANNING"
}
```

### Execution Blueprint Contract
Required fields:
- `schema_version`
- `execution_blueprint_id`
- `run_id`
- `status`
- `components`
- `dependencies`
- `build_groups`
- `validation_plan_ref`
- `completion_criteria_ref`
- `capability_mode`
- `planning_version`

Contract rules:
- blueprint is the canonical build intent
- every build group must resolve to declared components
- dependencies must not rely on undocumented shortcuts
- completion criteria and validation plan must exist before build begins

Ownership:
- instruQtor

Handoff semantics:
- handed from instruQtor to construQtor, validators, realization, and inspeQtor
- reused by repair only when repair plan explicitly says planning reuse is allowed

Schema example:
```json
{
  "schema_version": "execution-blueprint.v1",
  "execution_blueprint_id": "plan-001",
  "run_id": "run-001",
  "status": "PLANNING",
  "components": [
    "auth-service",
    "api-layer"
  ],
  "dependencies": [
    {
      "from": "api-layer",
      "to": "auth-service",
      "type": "runtime_call"
    }
  ],
  "build_groups": [
    {
      "build_group_id": "bg-auth",
      "components": ["auth-service"]
    }
  ],
  "validation_plan_ref": ".qonqrete/runs/run-001/planning/validation-plan.v1.json",
  "completion_criteria_ref": ".qonqrete/runs/run-001/planning/completion-criteria.v1.json",
  "capability_mode": "EXECUTION",
  "planning_version": 1
}
```

### Component Contract
Required fields:
- `schema_version`
- `component_id`
- `run_id`
- `status`
- `inputs`
- `outputs`
- `dependencies`
- `constraints`
- `owned_scopes`
- `interface_refs`

Contract rules:
- every component must declare owned scopes or owned files
- dependencies must be explicit
- interfaces consumed or exposed must be explicit
- construQtor may not mutate a component outside its owned scope without explicit plan change

Ownership:
- instruQtor

Handoff semantics:
- canonical component boundary contract from planning to build and validation

Schema example:
```json
{
  "schema_version": "component-contract.v1",
  "component_id": "auth-service",
  "run_id": "run-001",
  "status": "PLANNING",
  "inputs": [
    "login_request",
    "token_validation_request"
  ],
  "outputs": [
    "auth_token",
    "token_validation_result"
  ],
  "dependencies": [
    "user-store"
  ],
  "constraints": [
    "must not call external APIs directly"
  ],
  "owned_scopes": [
    "component-group:auth-service"
  ],
  "interface_refs": [
    ".qonqrete/runs/run-001/planning/dependency-contract.v1.json#auth-service"
  ]
}
```

### Build Report Contract
Required fields:
- `schema_version`
- `build_report_id`
- `run_id`
- `build_group_id`
- `status`
- `files`
- `changed_files`
- `assumptions_used`
- `scope_id`
- `write_strategy`
- `capability_mode`

Contract rules:
- every build report must cite the exact scope it touched
- changed files must distinguish intended and actual touched files where possible
- status must not imply correctness beyond build completion
- write strategy must be explicit

Ownership:
- construQtor

Handoff semantics:
- handed from construQtor to validators, realization, manifest, and inspeQtor

Schema example:
```json
{
  "schema_version": "build-report.v1",
  "build_report_id": "build-report-001",
  "run_id": "run-001",
  "build_group_id": "bg-auth",
  "status": "BUILDING",
  "files": [
    "src/auth/service.py",
    "src/auth/tokens.py"
  ],
  "changed_files": [
    {
      "path": "src/auth/service.py",
      "change_type": "modified"
    },
    {
      "path": "src/auth/tokens.py",
      "change_type": "created"
    }
  ],
  "assumptions_used": [
    "asm-001"
  ],
  "scope_id": "scope_build_group_auth",
  "write_strategy": "direct_with_recovery_risk",
  "capability_mode": "EXECUTION"
}
```

### Validation Result Bundle Contract
Required fields:
- `schema_version`
- `validation_bundle_id`
- `run_id`
- `status`
- `validation_execution_mode`
- `syntax`
- `tests`
- `details`
- `executed`
- `coverage`
- `capability_disclosure`

Contract rules:
- executed validation and simulated validation must be distinguishable
- missing coverage must be explicit
- deterministic failures cannot be hidden inside summary prose
- status must reflect actual validator outcome, not desired outcome

Ownership:
- System Validators

Handoff semantics:
- handed from validators to realization, manifest, and inspeQtor

Schema example:
```json
{
  "schema_version": "validation-bundle.v1",
  "validation_bundle_id": "validation-001",
  "run_id": "run-001",
  "status": "PARTIAL",
  "validation_execution_mode": "STATIC_ONLY",
  "syntax": "passed",
  "tests": "not_executed",
  "details": [
    {
      "check_id": "python-syntax",
      "result": "passed"
    },
    {
      "check_id": "integration-tests",
      "result": "not_executed"
    }
  ],
  "executed": false,
  "coverage": {
    "universal_checks": ["changed-file-truth"],
    "language_specific_checks": ["python-syntax"],
    "missing_checks": ["integration-tests", "runtime-startup"]
  },
  "capability_disclosure": {
    "language_strength": "python_strong_non_python_weaker",
    "notes": [
      "No executed tests were run for this build scope"
    ]
  }
}
```

### Result / Realization Bundle Contract
Required fields:
- `schema_version`
- `realization_bundle_id`
- `run_id`
- `status`
- `touched_scope`
- `changed_files`
- `structural_changes`
- `behavioral_outcomes`
- `system_impacts`
- `evidence_refs`
- `confidence`
- `validation_ref`
- `build_refs`

Contract rules:
- realization describes what happened, not what was intended
- structural, behavioral, and system impacts must be separated when evidence exists
- realization must be emitted before canonical inspection verdict
- missing evidence lowers confidence and must be explicit

Ownership:
- Result / Realization layer

Handoff semantics:
- handed from realization stage to inspeQtor and manifest

Schema example:
```json
{
  "schema_version": "realization-bundle.v1",
  "realization_bundle_id": "realization-001",
  "run_id": "run-001",
  "status": "EVIDENCE_PARTIAL",
  "touched_scope": [
    "component-group:auth-service"
  ],
  "changed_files": [
    "src/auth/service.py",
    "src/auth/tokens.py"
  ],
  "structural_changes": [
    "Created token utility module",
    "Modified auth service implementation"
  ],
  "behavioral_outcomes": [
    "No executed runtime behavior available",
    "Static validation passed for Python syntax"
  ],
  "system_impacts": [
    "Auth component API surface expanded with token helper usage"
  ],
  "evidence_refs": [
    ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json",
    ".qonqrete/runs/run-001/validation/validation-bundle.v1.json"
  ],
  "confidence": "CONFIDENCE_MEDIUM",
  "validation_ref": ".qonqrete/runs/run-001/validation/validation-bundle.v1.json",
  "build_refs": [
    ".qonqrete/runs/run-001/build/groups/bg-auth/build-report.v1.json"
  ]
}
```

### Inspection Verdict Contract
Required fields:
- `schema_version`
- `inspection_verdict_id`
- `run_id`
- `status`
- `issues`
- `repair_required`
- `confidence`
- `evidence_status`
- `completion_assessment`
- `next_lifecycle_transition`

Contract rules:
- verdict must cite evidence basis
- `repair_required=true` requires a Repair Plan artifact
- confidence must reflect validation depth and realization completeness
- verdict must not claim success beyond available evidence

Ownership:
- inspeQtor

Handoff semantics:
- handed from inspeQtor to manifest and repair flow

Schema example:
```json
{
  "schema_version": "inspection-verdict.v1",
  "inspection_verdict_id": "verdict-001",
  "run_id": "run-001",
  "status": "PARTIAL",
  "issues": [
    {
      "issue_id": "issue-001",
      "summary": "Integration tests were not executed",
      "severity": "high"
    }
  ],
  "repair_required": true,
  "confidence": "CONFIDENCE_MEDIUM",
  "evidence_status": "EVIDENCE_PARTIAL",
  "completion_assessment": "Planned auth component changes are present, but completion cannot be fully confirmed without executed validation.",
  "next_lifecycle_transition": "REPAIRING"
}
```

### Repair Plan Contract
Required fields:
- `schema_version`
- `repair_plan_id`
- `source_run_id`
- `source_verdict_ref`
- `repair_reason_summary`
- `target_components`
- `target_scopes`
- `required_actions`
- `planning_reuse_mode`
- `repair_pass_index`
- `repair_constraints`
- `validation_requirements_for_repair`
- `next_lifecycle_transition`
- `manifest_refs`
- `evidence_refs`

Contract rules:
- repair plan is first-class and required when repair is canonical
- repair plan must be scoped
- repair plan must not silently expand architecture or run scope
- repair plan replaces `reqap -> next tasq` as canonical continuation artifact
- repair plan must cite source verdict and evidence

Ownership:
- inspeQtor

Handoff semantics:
- handed from inspeQtor to runtime/orchestrator and construQtor for bounded repair execution

Schema example:
```json
{
  "schema_version": "repair-plan.v1",
  "repair_plan_id": "repair-plan-001",
  "source_run_id": "run-001",
  "source_verdict_ref": ".qonqrete/runs/run-001/verdict/inspection-verdict.v1.json",
  "repair_reason_summary": "Targeted contract and validation failures require scoped repair.",
  "target_components": ["auth-service"],
  "target_scopes": ["component-group:auth-service"],
  "required_actions": [
    "update component implementation",
    "re-run scoped validation",
    "re-run inspection for affected scope"
  ],
  "planning_reuse_mode": "reuse_locked_plan",
  "repair_pass_index": 1,
  "repair_constraints": [
    "no architecture mutation",
    "no scope expansion"
  ],
  "validation_requirements_for_repair": [
    "syntax validation",
    "component coherence validation",
    "required tests for affected scope"
  ],
  "next_lifecycle_transition": "REPAIRING",
  "manifest_refs": [
    ".qonqrete/runs/run-001/run-manifest.v1.json"
  ],
  "evidence_refs": [
    ".qonqrete/runs/run-001/verdict/inspection-verdict.v1.json"
  ]
}
```

### Run Manifest Contract
Required fields:
- `schema_version`
- `run_id`
- `stage`
- `lifecycle_status`
- `run_status`
- `stages`
- `artifacts`
- `timestamps`
- `capability_mode`
- `validation_execution_mode`
- `lineage`

Contract rules:
- manifest is created at intake
- manifest is updated at every stage transition
- manifest is authoritative linkage layer
- manifest must preserve lineage and compatibility references
- manifest must use canonical enums

Ownership:
- Runtime / Orchestrator

Handoff semantics:
- shared authoritative contract for all stages and artifacts

Schema example:
```json
{
  "schema_version": "run-manifest.v1",
  "run_id": "run-001",
  "stage": "INSPECTION",
  "lifecycle_status": "INSPECTING",
  "run_status": "RUN_ACTIVE",
  "stages": [
    {
      "stage_id": "INTAKE",
      "status": "completed"
    },
    {
      "stage_id": "CLARIFICATION",
      "status": "completed"
    }
  ],
  "artifacts": {
    "task_spec": ".qonqrete/runs/run-001/task/task-spec.v1.json",
    "execution_blueprint": ".qonqrete/runs/run-001/planning/execution-blueprint.v1.json",
    "inspection_verdict": ".qonqrete/runs/run-001/verdict/inspection-verdict.v1.json"
  },
  "timestamps": {
    "created_at": "2026-04-10T14:30:15Z",
    "updated_at": "2026-04-10T14:38:12Z"
  },
  "capability_mode": "MIXED_REASONING_EXECUTION",
  "validation_execution_mode": "MIXED",
  "lineage": {
    "parent_run_id": null,
    "continued_from_run_id": null
  }
}
```

### Continuation Metadata Contract
Required fields:
- `schema_version`
- `continuation_id`
- `source_run_id`
- `resume_point`
- `planning_reuse_mode`
- `continuation_reason`
- `next_run_id`

Contract rules:
- continuation metadata is required when work continues across run boundaries
- continuation must not hide whether planning is reused or superseded
- continuation cannot bypass manifest lineage

Ownership:
- Runtime / Orchestrator

Handoff semantics:
- handed from prior run terminal or continuable state into new linked run

Schema example:
```json
{
  "schema_version": "continuation-metadata.v1",
  "continuation_id": "cont-001",
  "source_run_id": "run-001",
  "resume_point": "REPAIRING",
  "planning_reuse_mode": "reuse_locked_plan",
  "continuation_reason": "Scoped repair continuation for auth-service",
  "next_run_id": "run-002"
}
```

## Dependency & Interaction Map
Agent-to-agent links:
- Runtime -> Qrystallizer: allowed
- Qrystallizer -> Guard: allowed
- Guard -> instruQtor: allowed
- instruQtor -> construQtor: allowed
- instruQtor -> System Validators: allowed only through Validation Plan and Execution Blueprint
- construQtor -> System Validators: allowed as execution handoff, not as judgment source
- System Validators -> Result / Realization: allowed
- Result / Realization -> inspeQtor: allowed
- inspeQtor -> Repair Plan: allowed
- Repair Plan -> construQtor: allowed through Runtime
- Runtime -> all stages: allowed for sequencing and manifest updates

Component-to-component links:
- only those declared in the dependency and interaction contract
- direct undeclared calls are forbidden
- dependency direction must be explicit
- ownership boundaries must remain explicit

System-to-agent links:
- Run Manifest links every major artifact and stage
- Runtime may read all canonical artifacts
- Validators may read plan, scope, and build outputs but may not rewrite planning artifacts
- inspeQtor may read all evidence artifacts but may not mutate build outputs

Forbidden shortcuts:
- raw Task Input -> construQtor as canonical build truth
- construQtor -> inspection verdict without validation and realization
- inspeQtor -> direct code mutation
- validators -> planning mutation
- Qrystallizer -> direct build initiation without Guard and planning
- `reqap` -> next task as canonical continuation
- legacy stage names as hidden canonical IDs

Allowed boundary crossings:
- compatibility-only qage artifacts may be linked into canonical manifest
- repair may reuse locked plan when repair plan explicitly declares reuse
- build may use component contracts and dependency contracts together
- validation may reuse effective constraints from Guard

## Data Flow Model
Canonical target flow:
1. Intake captures raw task input and creates run manifest.
2. Qrystallizer emits Qrystalized Task Spec and readiness state.
3. Guard validates policy and emits effective constraints.
4. instruQtor emits Execution Blueprint, Dependency & Interaction Contract, Component Contracts, Validation Plan, and Completion Criteria.
5. Estimation emits cost and optional gate data.
6. construQtor executes build groups within explicit scope.
7. System Validators emit Validation Result Bundle.
8. Result / Realization emits observed outcome bundle.
9. inspeQtor emits Inspection Verdict and Repair Plan when needed.
10. Runtime finalizes or routes to repair / continuation.

Current compatibility flow:
1. Task copied into qage `tasq.md`
2. `tasqleveler` may rewrite task
3. `instruqtor` emits briqs and contract
4. `construqtor` writes directly into `qodeyard/`
5. `inspeqtor` performs checks and emits `reqap`
6. `promote_reqap()` may create next cycle task

Bridge-flow references:
- raw task intake may still originate from `tasq.md`
- compatibility qage outputs may be mapped into canonical artifacts
- `tasqleveler` may exist only as compatibility clarification residue
- `reqap` may exist as legacy verdict evidence but not as canonical continuation driver

Gates and checkpoints:
- readiness gate after Qrystallizer
- guard gate before planning
- optional estimation gate before build
- optional repair approval gate before repair
- no mid-run clarification checkpoints after build starts

Repair-pass flow:
1. inspeQtor emits Repair Plan
2. Runtime checks repair cap and gating
3. construQtor executes scoped repair only
4. validators re-run for affected scope
5. realization updates affected outcome evidence
6. inspeQtor re-judges only the necessary scope and overall completion state

Explicit relationship between realization, verdict, repair plan, continuation metadata, and lifecycle transitions:
- realization records actual outcomes
- verdict judges realization plus validation against plan
- repair plan translates non-terminal verdicts into bounded corrective intent
- continuation metadata links cross-run follow-up when work moves beyond the current run
- lifecycle transitions are owned by runtime and must be manifest-linked

## Responsibility Separation
AI:
- Qrystallizer
- instruQtor
- inspeQtor
- construQtor when AI-backed build engines are used

Deterministic system:
- system validators
- runtime lifecycle enforcement
- manifest updates
- capability disclosure enforcement
- write-scope enforcement

Validators:
- own deterministic syntax, execution, test, mechanical, and contract checks where implemented
- do not own business completion judgment

Audit / logging:
- Run Manifest is authoritative linkage
- audit artifacts summarize and expose details
- logs are evidence, not standalone authority

Orchestration:
- runtime controls order, gating, stage transitions, repair caps, continuation linkage, and terminal states
- orchestration may not silently transfer authority between stages

## Validation Ownership Matrix
- syntax: System Validators
- parseability / static mechanical checks: System Validators
- tests / executed validation: System Validators
- policy gating before plan: Guard
- policy validation during or after build where implemented: System Validators referencing Guard constraints
- architecture definition: instruQtor
- architecture conformance judgment: inspeQtor using plan plus validation and realization evidence
- contract conformance:
  - declared by instruQtor
  - guarded pre-plan by Guard where applicable
  - mechanically checked by System Validators where implemented
  - finally judged by inspeQtor
- completion judgment: inspeQtor
- lifecycle status updates: Runtime / Orchestrator
- evidence completeness status: Result / Realization plus Runtime linkage
- capability disclosure: Runtime and System Validators, consumed by inspeQtor

## Execution Boundaries
What each part may do:
- Qrystallizer may clarify, ask bounded questions, and emit assumptions
- Guard may block, warn, and emit effective constraints
- instruQtor may define architecture, build groups, interfaces, dependencies, validation plan, and completion criteria
- construQtor may modify only declared build scope and emit build evidence
- validators may run deterministic checks and tests within configured execution boundaries
- realization may record outcomes and evidence
- inspeQtor may judge and propose repair
- runtime may sequence, gate, and update manifest state

What each part may never do:
- no mid-run questioning outside Qrystallizer
- no architecture rewriting by builders
- no hidden decision-making by runtime or build tools
- no silent capability downgrade without disclosure
- no false language-agnostic validation claims
- no direct build mutation by inspeQtor
- no direct verdict issuance by construQtor
- no silent stage skipping when required artifacts are missing
- no hidden cycle promotion as canonical continuation
- no use of logs alone as authoritative state

No hidden decision-making:
- every automatic mode or scope decision must be represented in canonical artifacts or manifest stage records

No architecture rewriting by builders:
- construQtor may implement the plan, not redesign it
- any architecture change requires explicit planning-stage supersession or new continuation plan

No silent capability downgrade:
- switching from executed validation to simulated validation must be explicit in artifacts and manifest
- switching from strong execution mode to weaker mode must be surfaced before verdict

No false language-agnostic validation claims:
- artifacts and verdicts must disclose where coverage is Python-strong or ecosystem-weak
- missing deterministic coverage lowers confidence

## Repo / File Contracts
Expected docs:
- current-state analysis
- execution plan
- hard ruleset
- migration compound
- Qonscience
- later documents may reference these, but Qonscience owns system contract structure

Expected state location:
- canonical runtime state under `.qonqrete/`
- current qage structure remains compatibility-only during migration
- support/cache artifacts must not be confused with authoritative run artifacts

Naming expectations:
- machine-readable canonical artifacts should use stable schema/versioned names
- stage names and statuses must use canonical registry values in machine-readable artifacts
- legacy names may appear only as compatibility aliases or legacy links

Persistence boundaries:
- repo working tree remains user code source of truth
- `.qonqrete` remains QonQrete state source of truth
- cache/support artifacts may exist but must be linked and categorized explicitly

Artifact ownership:
- task artifacts: intake and Qrystallizer
- guard artifacts: Guard
- planning artifacts: instruQtor
- build artifacts: construQtor
- validation artifacts: System Validators
- realization artifacts: Result / Realization
- verdict and repair artifacts: inspeQtor
- manifest and continuation metadata: Runtime / Orchestrator

Manifest linkage:
- every canonical artifact must be linkable from the Run Manifest
- orphan canonical artifacts are invalid
- legacy artifacts must be linked through manifest if relied upon during migration

Relationship to `.qonqrete/`:
- `.qonqrete/` is canonical state root in target state
- qage content may be mirrored or linked into `.qonqrete` during transition
- canonical artifacts should be emitted there even when legacy copies remain

Relationship between support/cache artifacts and authoritative artifacts:
- cache manifests are not run manifests
- support artifacts like `qontext`, `bloq`, or cache payloads are supporting evidence or services, not authoritative lifecycle carriers
- support artifacts must be categorized explicitly and linked if used in decisions

## Language / Ecosystem Capability Disclosure
Universal validation behaviors:
- manifest linkage
- changed-file truth
- build scope declaration
- capability disclosure
- artifact completeness checks
- lifecycle and status integrity
- distinction between simulated and executed validation

Language / ecosystem specific validation behaviors:
- syntax parsing
- compile/build checks
- executed tests
- AST-based rules
- ecosystem-specific contract enforcement
- runtime startup or integration checks where tooling exists

Current stronger Python-centric flows:
- `loqal_verifier` is Python-only
- `qontract_guard` is Python AST-based
- `qompressor` and `qontextor` have stronger Python-specific deterministic behavior
- broader deterministic compile/test loops are weaker or absent outside Python in current reality

Weaker ecosystem support disclosure requirements:
- every Validation Result Bundle must disclose missing checks
- every capability disclosure must state whether validation was simulated, static-only, executed, or mixed
- every verdict confidence must reflect real coverage limits
- every runtime state used for user-facing reporting must avoid parity claims that do not exist

Capability modes and validation depth claims:
- `SIMULATION` means no real execution authority
- `EXECUTION` means executed build or validation is available
- `MIXED_REASONING_EXECUTION` means some stages reason and some execute
- capability claims must match artifact evidence
- stronger and weaker modes must be visible in Task Spec, plan artifacts where relevant, validation bundle, manifest, and verdict interpretation

## Schema Versioning Appendix
All machine-readable artifacts MUST include `schema_version`.

Version mismatch handling:
- readers must validate declared `schema_version`
- unsupported versions must fail explicitly or route through compatibility adapters
- silent best-effort parsing of incompatible canonical artifacts is forbidden

Backward compatibility / coexistence rules:
- machine-readable canonical artifacts may coexist with legacy artifacts during migration
- canonical schema-versioned artifacts win when they conflict with unversioned or legacy equivalents
- compatibility adapters may map legacy artifacts into canonical contract domains, but they must not silently claim the legacy artifact already satisfies the new schema
- manifest should record both canonical and legacy paths when both exist

Ownership:
- schema versioning is a Qonscience contract concern
- migration docs may reference version coexistence, but Qonscience owns the canonical contract rule that machine-readable artifacts are versioned
- later contract documents may extend schemas, but should not redefine the requirement for versioning or the coexistence rule model

Recommended canonical version labels:
- `task-input.v1`
- `task-spec.v1`
- `guard-result.v1`
- `execution-blueprint.v1`
- `component-contract.v1`
- `build-report.v1`
- `validation-bundle.v1`
- `realization-bundle.v1`
- `inspection-verdict.v1`
- `repair-plan.v1`
- `run-manifest.v1`
- `continuation-metadata.v1`

## Inconsistencies or Open Structural Risks
- current codebase still contains `tasqleveler` and no Qrystallizer implementation, so clarification authority is not yet embodied in code
- current runtime still treats qage as the practical state source of truth, while target Qonscience defines `.qonqrete` as canonical
- current continuation logic still relies on `reqap -> next tasq` promotion, which conflicts with canonical Repair Plan authority
- current docs, comments, and runtime stage order do not fully align
- current `QontractGuard` behavior is Python-specific and appears late or per-briq today, while Qonscience defines a pre-plan guard authority
- current validation reality is Python-strong and non-Python-weaker, so any broader contract conformance language must remain qualified
- current build writes are incremental and non-transactional, which means Qonscience write-boundary contracts are not yet fully enforced in implementation
- current audit is fragmented, and logs or markdown summaries may still be the practical evidence source until manifest linkage is complete
- current helper stages such as `qontextor`, `qompressor`, and `qontrabender` are not yet fully classified as canonical stages versus support services
- current cache manifest behavior risks confusion with the missing canonical run manifest if naming and storage remain unclear
