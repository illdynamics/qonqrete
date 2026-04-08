# QonQrete Qonscience

## Purpose of Qonscience

Qonscience is the authoritative structural and relational contract layer for QonQrete. It defines how system parts relate, what each part owns, what each handoff must contain, where decisions are allowed, where they are forbidden, how evidence moves from task intake to final verdict, and which artifact becomes the source of truth at each phase.

Qonscience connects:
- the current implemented runtime and artifact layout
- the intended target-stage architecture
- the hard operational rules
- the migration bridge from qage/cycle behavior to repo-native single-pass behavior

Qonscience is not a migration plan, not a ruleset rewrite, and not a target-state restatement. It is the authoritative contract model for:
- interfaces
- dependencies
- ownership
- handoffs
- authority boundaries
- persistence boundaries
- evidence boundaries

## System Relationship Model

QonQrete is a system-owned orchestration authority with bounded AI stages and deterministic validation services.

Core relationship rules:
- The system owns orchestration, sequencing, gating, persistence, repair caps, continuation state, audit linkage, and final runtime control.
- AI stages own bounded reasoning or bounded execution only within explicit contracts.
- Deterministic validators own mechanical truth checks and executed evidence.
- Clarification authority, planning authority, execution authority, validation authority, judgment authority, and persistence authority are separate concerns.
- Downstream stages must consume structured artifacts, not rely on prose interpretation alone.
- No agent may silently redefine architecture, constraints, dependency wiring, completion criteria, or repair scope after planning is locked.
- Support/context/cache helpers may enrich execution context, but they may not become hidden planning authorities or hidden verdict authorities.
- Current multi-cycle transport exists in implementation, but the canonical contract model is single-pass plus targeted repair.

System authority hierarchy:
1. Orchestrator/runtime authority and system contracts
2. Deterministic validation evidence and guard outcomes
3. Locked planning artifacts
4. AI execution artifacts
5. AI judgment artifacts

System contract principles:
- Ask once, in clarification only.
- Plan before code generation.
- Validate mechanically before final judgment.
- Repair by target scope, not by whole-run loop.
- Persist one authoritative run record linking all artifacts.
- Keep repo code as code truth and QonQrete state as run/evidence truth.

## Transition Boundary Notes

### Current reality

Current implementation reality is:
- repo-local, containerized, file-driven runtime
- per-run `worqspace/qage_*` state root
- cycle-based orchestration through `qrane.py`
- YAML-defined stage order
- `tasqleveler` present, optional, cycle-1-only
- `Qrystallizer` absent
- standalone `Qualifier` absent
- `instruqtor`, `construqtor`, `inspeqtor`, `calqulator`, `qontextor`, `qompressor`, `qontrabender`, `qontract_guard`, and `loqal_verifier` present
- cycle progression implemented as `reqap.d/cyqleN_reqap.md -> tasq.d/cyqleN+1_tasq.md`
- deterministic validation exists and is strongest for Python-centric flows
- audit/evidence is fragmented across markdown artifacts, logs, event logs, IDE markers, and optional cache ledgers

### Target-state contract

Canonical target contract is:
- repo-native `.qonqrete/` state root
- one clarify/guard/plan/estimate/build/validate/judge flow
- `Qrystallizer` as sole ambiguity-clearing front door
- pre-plan guard/policy validation as first-class stage
- stable planning package as the execution authority
- component-group build model with internal mini-briqs
- validator bundles as first-class evidence artifacts
- `Inspeqtor` issuing `done` or `repair required`
- bounded targeted repair instead of default whole-cycle reruns
- one authoritative run manifest linking artifacts, statuses, costs, audit, validation, verdict, and continuation state

### Transitional bridge behavior

Bridge behavior during migration is:
- qage-local state may coexist with `.qonqrete/` state
- `tasqleveler` may remain in code temporarily but is treated as deprecated and non-canonical
- current deterministic validators remain valid transitional execution units
- `reqap` may remain as a readable review artifact, but it is not the canonical next-task transport in the target model
- support helpers such as `qontextor`, `qompressor`, and `qontrabender` remain support services, not authorities
- current multi-cycle promotion is treated as an implementation-era transport mechanism, not the desired long-term contract

Verified current inconsistencies that must not be silently normalized:
- `worqspace/pipeline_config.yaml` header comments describe `instruqtor -> calqulator -> construqtor -> inspeqtor -> qontextor -> qompressor`, but the actual configured order is `tasqleveler -> instruqtor -> calqulator -> construqtor -> qontextor -> qompressor -> qontrabender -> inspeqtor`
- `qrane/paths.py` defines `qache_dir` as `sqrapyard/qache.d`, while pipeline config and runtime descriptions treat `qache.d/` as a qage/run artifact
- historical artifacts under `worqspace/qage_20260402_172204/` reference an alternative `Qrystallizer/Qualifier` concept; these are historical experiments, not current contract truth

## Agent Contracts

### tasQleveler / Qrystallizer Transition Contract

Input:
- Current raw task content from `tasq.d/cyqle1_tasq.md`
- Optional workspace/task context
- Current qage/cycle context during compatibility flow

Output:
- Current reality: optionally rewritten cycle-1 task text
- Target bridge expectation: structured clarified task artifact that can feed planning
- Transition status signal: deprecated clarification path vs canonical clarification path

Responsibilities:
- Preserve downstream ability to feed planning while clarification architecture is migrating
- Mark `tasqleveler` as transitional residue, not structural authority
- Ensure long-term clarification behavior moves toward structured readiness assessment, not heuristic document rewrite

Must NOT:
- Become a long-term canonical front door
- Remain required for planning in the target contract
- Coexist indefinitely with `Qrystallizer` as equal authorities
- Define post-clarification planning truth

Authority boundary:
- Current code may still execute `tasqleveler`
- Canonical clarification authority belongs only to `Qrystallizer`
- Any task enhancement by `tasqleveler` is compatibility behavior, not target contract behavior

### Qrystallizer

Input:
- Raw task input artifact
- User-provided task file path or task content origin
- Allowed repo context signals
- Optional continuation context
- Default policy baseline and configured overrides relevant to clarification

Output:
- `Qrystalized Task Spec`
- Readiness state: `READY` or `NOT_READY`
- Locked assumptions
- Blocking gaps
- Non-blocking unknowns
- Critical decisions confirmed

Responsibilities:
- Extract objective, constraints, known inputs, desired outcomes, and material unknowns
- Detect only high-impact gaps
- Ask bounded questions once before execution
- Convert low-impact unresolved ambiguity into explicit assumptions
- Produce a structured planning-ready artifact

Must NOT:
- Generate architecture
- Generate code
- Choose execution profile
- Run validators
- Ask questions after readiness is locked
- Turn into a broad interview or form-filling stage

Authority boundary:
- Owns clarification only
- Is the only stage allowed to ask the user questions
- Cannot authorize planning or build on `NOT_READY`
- Cannot redefine scope after output is locked

### Instruqtor

Input:
- `READY` `Qrystalized Task Spec`
- `Guard Result` effective constraints
- Allowed repo/codebase context for planning
- Capability mode and system execution limits
- Optional continuation/repair scope

Output:
- `Execution Blueprint / Planning Package`
- Architecture Foundation
- Execution Plan
- Dependency & Interaction Contract
- Component Contracts
- Validation Plan
- Completion Criteria
- Execution shape metadata
- Repair allowance metadata

Responsibilities:
- Convert clarified intent into a stable build design
- Define component boundaries, interfaces, dependencies, and forbidden shortcuts
- Select internal execution shape and batch profile
- Define validation expectations and completion criteria before build starts
- Produce planning artifacts that become authority for builders, validators, and `Inspeqtor`

Must NOT:
- Ask questions mid-run
- Redefine clarified user intent
- Delegate architecture decisions to builders
- Emit planning artifacts that are only narrative prose
- Treat independent global briq generation as sufficient architecture

Authority boundary:
- Owns planning authority
- Planning artifacts become the source of truth for downstream execution and judgment
- Cannot execute code or declare completion
- May be updated only through explicit repair-plan mechanics, not silent adaptation

### Constrqutor

Input:
- Locked planning package
- Current `Component Contract`
- Dependency & Interaction Contract
- Effective constraints
- Capability mode and execution boundaries
- Existing repo/qode state for scoped targets
- Optional repair-target scope

Output:
- Code and file modifications within allowed scope
- `Build Report` per component/group
- Changed-file manifest
- Execution summary
- Logged assumptions used during build

Responsibilities:
- Build by component group, not by isolated global briqs
- Use briqs only as internal construction units inside shared component context
- Preserve interface and dependency contract conformance while modifying code
- Perform immediate intra-component coherence checks before moving on
- Surface assumptions, touched interfaces, and local issues explicitly

Must NOT:
- Ask the user questions
- Redesign architecture
- Change dependency contracts
- Invent new completion criteria
- Expand scope beyond assigned component/group
- Substitute itself for validators or final judgment
- Bypass deterministic validation

Authority boundary:
- Owns scoped implementation only
- May mutate repo code only within assigned scope
- Cannot mutate planning truth or final verdict truth
- If external execution engines are used later, they act only as constrained workers inside `Constrqutor` authority

### Inspeqtor

Input:
- Locked planning package
- `Build Report` artifacts
- Changed-file manifests
- `Validation Result Bundle` artifacts
- Test outputs, or explicit non-executed validation disclosure
- Effective constraints
- Assumption records
- Optional repair history

Output:
- `Inspection Verdict`
- Status: `done` or `repair required`
- Repair targets
- Evidence references
- Residual risk notes
- Confidence conditioned by capability mode

Responsibilities:
- Judge implementation against Architecture Foundation, Dependency & Interaction Contract, Validation Plan, Completion Criteria, and validator evidence
- Determine whether repair is required and where
- Keep repair targeting scoped to affected components/groups
- Produce reasons tied to explicit evidence and criteria

Must NOT:
- Execute tests itself
- Replace deterministic validation
- Rescue vague upstream design by intuition
- Ask questions mid-run
- Declare completion without artifact and validator evidence
- Request global reruns by default

Authority boundary:
- Owns completion judgment and repair targeting only
- Cannot rewrite architecture or planning artifacts
- Cannot overrule deterministic validator failures silently
- Cannot become execution authority

### System Validators (Non-AI)

Input:
- Planned validation scope
- Changed-file manifests
- Build reports
- Repo state under allowed execution boundaries
- Contracts, policies, and mechanical rules
- Capability mode

Output:
- `Validation Result Bundle`
- Machine-readable results
- Condensed human-readable summary
- Test outputs where execution mode allows them

Responsibilities:
- Own syntax, parseability, import/interface/schema checks
- Own required artifact checks
- Own contract/policy/mechanical checks where deterministic logic exists
- Own grouped component coherence checks
- Own sandboxed test execution when enabled
- Produce objective evidence for `Inspeqtor` and audit

Must NOT:
- Plan architecture
- Decide user intent
- Declare overall completion by themselves
- Present heuristic AI judgment as mechanical proof
- Exist as a standalone AI `Qualifier` agent

Authority boundary:
- Own mechanical truth and executed truth only
- Cannot set planning authority or final verdict authority
- May fail or warn on evidence, but interpretation of overall completion remains with `Inspeqtor`

### Guard / Policy Validation Stage

Input:
- `Qrystalized Task Spec`
- Default policy baseline
- Configured policy overrides
- Security/operational boundary rules
- Optional repo-specific constraints

Output:
- `Guard Result`
- Status: `pass`, `fail`, or `review`
- Blocking issues
- Warnings
- Effective constraints

Responsibilities:
- Validate clarified task before planning/building
- Detect policy, security, or boundary violations early
- Enrich downstream planning with effective constraints
- Represent pre-build constraint truth explicitly

Must NOT:
- Replace planning
- Rewrite user intent
- Produce architecture
- Hide degraded or unresolved policy states
- Be reduced to subjective AI review

Authority boundary:
- Owns pre-plan guard result
- May block planning on `fail`
- May pass constraints downstream on `pass` or non-blocking `review`
- Deterministic contract enforcement may continue later in validators, but early guard truth belongs here

### Orchestrator / Runtime Authority

Input:
- User command / run request
- Task input origin
- Configured runtime settings
- Pipeline/stage registry
- Continuation metadata
- Existing run state
- Capability mode and execution boundaries

Output:
- Run identity
- Stage sequencing and gating decisions
- Run manifest updates
- Audit timeline linkage
- Continuation state
- Final lifecycle status

Responsibilities:
- Own sequencing, stage order, checkpoints, gates, and repair caps
- Own manifest creation and lifecycle updates
- Own persistence wiring and artifact linkage
- Own continuation/resume state
- Own capability-mode disclosure
- Fail fast on missing required artifacts or invalid stage preconditions

Must NOT:
- Delegate orchestration authority to AI agents
- Hide retries, fallbacks, degraded modes, or repair-cap hits
- Allow mid-run user questioning outside `Qrystallizer`
- Let support artifacts become hidden planning or verdict truth
- Claim stronger validation/security guarantees than actual enforcement supports

Authority boundary:
- Highest runtime authority
- Decides when a stage may run
- Decides when a run may continue, repair, or terminate
- Does not itself generate architecture, code, or judgment content; it governs the flow and persists the truth

## Data Contracts

### Task Input Contract

Required fields:
- `task_input_id`
- `source_type`
- `source_path` or `inline_origin`
- `content`
- `repo_root`
- `user_constraints`
- `continuation_from_run` optional
- `created_at`

Contract rules:
- Raw task input is allowed to be incomplete or ambiguous
- Task input is not execution-ready by default
- User constraints are explicit only; unstated assumptions are not injected here
- This is the only stage where ambiguity may exist before clarification

Ownership:
- Owned by orchestrator/runtime authority as intake artifact

Handoff semantics:
- Passed to `Qrystallizer`
- Never used directly by `Constrqutor` as authoritative planning input

### Qrystalized Task Spec Contract

Required fields:
- `spec_id`
- `task_input_id`
- `goal`
- `known_inputs`
- `constraints`
- `locked_assumptions`
- `critical_decisions_confirmed`
- `blocking_gaps`
- `non_blocking_unknowns`
- `readiness`
- `clarification_log_refs`

Contract rules:
- This is the only artifact allowed to carry pre-execution ambiguity resolution
- `READY` is required before planning
- `NOT_READY` blocks planning and building
- After this artifact is locked, ambiguity becomes assumptions, not questions
- All later stages must treat this as the clarified task truth

Ownership:
- Owned by `Qrystallizer`

Handoff semantics:
- Passed to Guard / Policy Validation Stage
- Passed to `Instruqtor` only when readiness permits

Schema example:
```yaml
spec_id: qts_2026_04_08_001
task_input_id: task_2026_04_08_001
goal: "Add token-based auth to the existing API service"
known_inputs:
  repo_context:
    repo_root: /repo
    primary_language: python
  task_file: tasks/add-auth.md
  explicit_requirements:
    - "Use existing FastAPI app"
    - "Preserve current public routes"
constraints:
  explicit:
    - "Do not add external auth provider dependency"
  inherited_policy:
    - "No networked test execution"
locked_assumptions:
  - "Use repo-default test runner"
  - "Reuse existing user model if compatible"
critical_decisions_confirmed:
  - "Token auth is sessionless bearer auth"
blocking_gaps: []
non_blocking_unknowns:
  - "Exact token expiry window not specified"
readiness: READY
clarification_log_refs:
  - artifacts/task/clarification-log.jsonl
```

### Guard Result Contract

Required fields:
- `guard_result_id`
- `spec_id`
- `status`
- `blocking_issues`
- `warnings`
- `effective_constraints`
- `policy_version`
- `review_required` optional
- `generated_at`

Contract rules:
- Guard runs after clarification and before planning
- `fail` blocks planning
- `review` may proceed only if non-blocking under orchestrator policy
- Effective constraints become downstream planning/build inputs
- Guard results must distinguish blocking from advisory findings

Ownership:
- Owned by Guard / Policy Validation Stage

Handoff semantics:
- Passed to `Instruqtor`
- Indexed in run manifest
- Remains part of audit evidence for `Inspeqtor`

Schema example:
```yaml
guard_result_id: guard_2026_04_08_001
spec_id: qts_2026_04_08_001
status: pass
blocking_issues: []
warnings:
  - "Requested security scope touches auth-critical files"
effective_constraints:
  - "No new outbound network dependencies"
  - "All auth changes must preserve current route contracts"
  - "Tests must run in no-network mode"
policy_version: default-qontract-policy-v1
review_required: false
generated_at: 2026-04-08T14:30:00Z
```

### Execution Blueprint / Planning Package Contract

Required fields:
- `plan_id`
- `spec_id`
- `guard_result_id`
- `architecture_foundation`
- `execution_plan`
- `dependency_interaction_contract`
- `component_contracts`
- `validation_plan`
- `completion_criteria`
- `execution_shape`
- `repair_allowance`
- `cost_estimate_ref` optional
- `created_at`

Contract rules:
- Must be stable before build starts
- Becomes the planning authority for builders, validators, and `Inspeqtor`
- May be updated only through explicit repair-plan mechanics
- Must define completion before code generation starts
- Dependency relationships are first-class contract content, not side notes

Ownership:
- Owned by `Instruqtor`

Handoff semantics:
- Passed to `Calqulator`, `Constrqutor`, validators, and `Inspeqtor`
- Indexed as a locked plan in the run manifest

Schema example:
```yaml
plan_id: plan_2026_04_08_001
spec_id: qts_2026_04_08_001
guard_result_id: guard_2026_04_08_001
architecture_foundation:
  summary: "Add auth middleware, token service, and protected route checks"
execution_plan:
  groups:
    - auth-service
    - api-integration
dependency_interaction_contract:
  ref: artifacts/plan/dependency-interaction-contract.md
component_contracts:
  - artifacts/plan/components/auth-service.yaml
  - artifacts/plan/components/api-integration.yaml
validation_plan:
  unit_tests:
    - "token service generation/validation"
  integration_tests:
    - "protected route rejects missing token"
  expected_behaviors:
    - "existing unprotected routes remain unchanged"
  failure_conditions:
    - "route contract regression"
completion_criteria:
  - "Token issuance and validation implemented"
  - "Protected routes enforce auth"
  - "Existing public routes remain passing"
execution_shape:
  model: component_groups_with_internal_mini_briqs
  briq_sense: medium
  capability_mode: simulation
repair_allowance:
  max_repair_passes: 2
created_at: 2026-04-08T14:35:00Z
```

### Component Contract

Required fields:
- `component_id`
- `plan_id`
- `inputs`
- `outputs`
- `interfaces`
- `dependencies`
- `allowed_collaborators`
- `forbidden_links`
- `constraints`
- `acceptance_conditions`

Contract rules:
- `Constrqutor` builds against this unit
- Validators verify coherence against this unit
- Components may depend only on declared interfaces and allowed collaborators
- Components must not bypass their declared boundary
- Acceptance conditions must be checkable by validators or `Inspeqtor`

Ownership:
- Owned by `Instruqtor` as part of planning package

Handoff semantics:
- Passed to `Constrqutor` for scoped execution
- Passed to validators for grouped coherence checks
- Passed to `Inspeqtor` for scope-aware judgment

Schema example:
```yaml
component_id: auth-service
plan_id: plan_2026_04_08_001
inputs:
  - "request credentials payload"
  - "existing user repository access"
outputs:
  - "signed auth token"
  - "auth verification result"
interfaces:
  exposes:
    - name: AuthService.issue_token
      input: Credentials
      output: TokenResult
    - name: AuthService.validate_token
      input: BearerToken
      output: AuthContext
dependencies:
  - user-repository
  - app-config
allowed_collaborators:
  - api-integration
forbidden_links:
  - direct-db-access-from-api-layer
constraints:
  - "No external auth provider"
  - "Preserve current route response shape"
acceptance_conditions:
  - "Token issue/validate paths implemented"
  - "Protected route flow can consume auth context"
```

### Build Report Contract

Required fields:
- `build_report_id`
- `plan_id`
- `component_scope`
- `changed_files`
- `work_summary`
- `assumptions_used`
- `touched_interfaces`
- `local_issues`
- `capability_mode`
- `output_artifacts`
- `completed_at`

Contract rules:
- Must describe what changed and why
- Must identify assumptions that affected output
- Must identify touched interfaces/dependencies
- Must be sufficient for downstream validation and audit
- Must reflect actual build scope, not planned scope only

Ownership:
- Owned by `Constrqutor`

Handoff semantics:
- Passed to validators
- Passed to `Inspeqtor`
- Indexed in run manifest and audit timeline

Schema example:
```yaml
build_report_id: build_auth_service_001
plan_id: plan_2026_04_08_001
component_scope:
  group_id: auth-service
  files_targeted:
    - app/auth/service.py
    - app/api/deps.py
changed_files:
  - app/auth/service.py
  - app/api/deps.py
work_summary:
  - "Added token issue/validate service"
  - "Added auth dependency helper for protected routes"
assumptions_used:
  - "Used existing config object for token secret lookup"
touched_interfaces:
  - "AuthService.issue_token"
  - "AuthService.validate_token"
local_issues:
  warnings:
    - "Token expiry default assumed from repo config naming convention"
  errors: []
capability_mode: simulation
output_artifacts:
  changed_manifest: artifacts/build/groups/auth-service/changed-files.json
  execution_log: artifacts/build/groups/auth-service/execution-log.txt
completed_at: 2026-04-08T14:48:00Z
```

### Validation Result Bundle Contract

Required fields:
- `bundle_id`
- `validator_id`
- `plan_id`
- `scope`
- `mode`
- `executed`
- `outcome`
- `violations`
- `warnings`
- `evidence_refs`
- `summary`
- `completed_at`

Contract rules:
- Must distinguish executed validation from simulated/non-executed validation
- Must not overclaim coverage
- Must remain deterministic and machine-consumable
- Must identify exact scope checked
- Violations and warnings must be attributable to evidence

Ownership:
- Owned by System Validators

Handoff semantics:
- Passed to `Inspeqtor`
- Indexed in run manifest
- Referenced by audit and final verdict

Schema example:
```yaml
bundle_id: validate_auth_service_syntax_001
validator_id: loqal_verifier
plan_id: plan_2026_04_08_001
scope:
  component_group: auth-service
  files:
    - app/auth/service.py
    - app/api/deps.py
mode: simulation
executed: false
outcome: pass
violations: []
warnings:
  - "Runtime behavior not executed in simulation mode"
evidence_refs:
  - artifacts/validation/bundles/validate_auth_service_syntax_001.json
summary: "Syntax and local import checks passed for auth-service scope"
completed_at: 2026-04-08T14:50:00Z
```

### Inspection Verdict Contract

Required fields:
- `verdict_id`
- `plan_id`
- `status`
- `repair_targets`
- `reasons`
- `evidence_refs`
- `residual_risks`
- `confidence`
- `generated_at`

Contract rules:
- Cannot be issued without validator evidence
- Cannot use vague intuition as sole basis
- Must target repair precisely
- Must disclose confidence conditioned by capability mode
- `done` and `repair required` are the only canonical statuses

Ownership:
- Owned by `Inspeqtor`

Handoff semantics:
- Passed to orchestrator/runtime authority
- Used to decide finish vs targeted repair
- Indexed in run manifest and audit

Schema example:
```yaml
verdict_id: verdict_2026_04_08_001
plan_id: plan_2026_04_08_001
status: repair_required
repair_targets:
  - api-integration
reasons:
  - "Protected route enforcement not yet wired on two planned endpoints"
  - "Validation evidence covers syntax but not executed integration behavior"
evidence_refs:
  - artifacts/build/groups/api-integration/build-report.json
  - artifacts/validation/bundles/route-contracts.json
residual_risks:
  - "Execution mode unavailable; runtime auth path not proven"
confidence: medium
generated_at: 2026-04-08T14:55:00Z
```

### Run Manifest Contract

Required fields:
- `run_id`
- `repo`
- `mode`
- `status`
- `inputs`
- `clarification`
- `guard`
- `planning`
- `estimation`
- `build`
- `validation`
- `inspection`
- `audit`
- `continuation`

Contract rules:
- One authoritative manifest exists per run
- Manifest is created before clarification starts
- Manifest is updated by orchestrator at each major stage boundary
- Manifest links all major artifacts and statuses together
- Manifest is the primary linkage/index object, not the source of code truth
- Completed runs remain continuable

Ownership:
- Owned by orchestrator/runtime authority

Handoff semantics:
- Read by runtime for continuation/resume
- Read by audit tooling
- Read by any later inspection/reporting layer
- Not treated as mutable planning content by builders

Schema example:
```yaml
run_id: run_2026_04_08T14_22_31Z_repo_slug_ab12cd
repo:
  root: /repo
  git_head: abc123def456
  task_input_path: tasks/add-auth.md
mode:
  capability_mode: simulation
  execution_mode: local_system
  repair_cap: 2
status:
  lifecycle: repairable
  current_stage: inspection
  final_verdict: null
inputs:
  task_input_artifact: artifacts/task/task-input.md
  continuation_from_run: null
clarification:
  status: ready
  artifact: artifacts/task/qrystalized-task-spec.yaml
  questions_asked: 3
guard:
  status: pass
  artifact: artifacts/guard/guard-result.yaml
planning:
  status: complete
  artifact_root: artifacts/plan
estimation:
  estimated_cost_usd: 4.83
  actual_cost_usd: 2.11
  confidence: medium
build:
  groups:
    - group_id: auth-service
      status: complete
      build_report: artifacts/build/groups/auth-service/build-report.yaml
validation:
  bundles:
    - artifacts/validation/bundles/validate_auth_service_syntax_001.yaml
inspection:
  status: repair_required
  artifact: artifacts/verdict/inspection-verdict.yaml
audit:
  timeline_artifact: artifacts/audit/timeline.jsonl
  deep_trace_artifact: artifacts/audit/deep-trace.jsonl
continuation:
  repair_passes_used: 0
  repair_targets:
    - api-integration
  next_action: repair
```

### Continuation Metadata Contract

Required fields:
- `continuation_id`
- `source_run_id`
- `continuation_type`
- `target_scope`
- `inherited_artifacts`
- `planning_reuse_mode`
- `repair_pass_count`
- `next_action`
- `created_at`

Contract rules:
- Continuation is manifest-based in the target model
- Completed runs may still be continuable
- Continuation must reference inherited truth explicitly rather than relying on implicit cycle promotion
- Continuation must declare whether planning is reused or refreshed
- Continuation must preserve repair-cap accounting

Ownership:
- Owned by orchestrator/runtime authority

Handoff semantics:
- Passed to runtime before next run step begins
- Indexed in run manifest
- May seed `Qrystallizer`, `Instruqtor`, or repair routing depending on continuation type

Schema example:
```yaml
continuation_id: cont_2026_04_08_001
source_run_id: run_2026_04_08T14_22_31Z_repo_slug_ab12cd
continuation_type: targeted_repair
target_scope:
  component_groups:
    - api-integration
inherited_artifacts:
  - artifacts/task/qrystalized-task-spec.yaml
  - artifacts/guard/guard-result.yaml
  - artifacts/plan
planning_reuse_mode: reuse_locked_plan
repair_pass_count: 1
next_action: rebuild_and_revalidate_target_scope
created_at: 2026-04-08T15:00:00Z
```

## Dependency & Interaction Map

### Agent-to-agent links

Allowed:
- `Task Input -> Qrystallizer`
- `Qrystallizer -> Guard / Policy Validation Stage`
- `Qrystallizer -> Instruqtor` only via `READY` clarified spec
- `Guard / Policy Validation Stage -> Instruqtor`
- `Instruqtor -> Calqulator`
- `Instruqtor -> Constrqutor`
- `Instruqtor -> System Validators`
- `Instruqtor -> Inspeqtor`
- `Constrqutor -> System Validators`
- `Constrqutor -> Inspeqtor`
- `System Validators -> Inspeqtor`
- `Inspeqtor -> Orchestrator / Runtime Authority`
- `Inspeqtor -> Constrqutor` only through targeted repair plan handoff
- `Orchestrator / Runtime Authority -> all stages` for gating, sequencing, manifest linkage, and continuation control

Forbidden shortcuts:
- `Constrqutor -> user`
- `Inspeqtor -> user` mid-run
- `System Validators -> planning artifact rewrite`
- `Constrqutor -> planning artifact rewrite`
- `Inspeqtor -> architecture rewrite`
- `Qrystallizer -> code modification`
- any direct AI-agent shortcut that bypasses guard result or validator evidence

### Component-to-component links

Allowed:
- Through declared interfaces in the Dependency & Interaction Contract
- Through planned dependency edges
- Through approved shared contract/config boundaries
- Through declared collaborator relationships in Component Contracts

Forbidden:
- Direct calls that bypass declared intermediary layers
- Hidden shortcuts from outer layers directly into deep internal layers
- Runtime coupling not declared in component contracts
- Builder-invented links absent from planning artifacts
- Validation-bypassing interface changes
- direct dependency injection that violates forbidden links

### System-to-agent links

System-owned decisions:
- stage order
- readiness gates
- guard enforcement gates
- repair caps
- capability mode disclosure
- persistence and manifest linkage
- audit format and timeline linkage
- deterministic validation boundaries
- continuation routing

AI-interpreted but not mechanically sovereign:
- gap detection reasoning
- architecture/planning synthesis
- scoped implementation choices within contract
- evidence-based completion judgment

Allowed boundary crossings:
- support helpers may provide context/cache artifacts to builders or validators
- support helpers may be indexed by manifest as auxiliary artifacts
- support helpers may not define planning, guard, or verdict truth

## Data Flow Model

### Canonical target flow

1. Task input enters system
2. `Qrystallizer` emits `Qrystalized Task Spec`
3. Guard stage validates clarified spec and emits `Guard Result`
4. `Instruqtor` emits locked `Execution Blueprint / Planning Package`
5. `Calqulator` estimates cost/execution shape and may support a pre-build gate
6. `Constrqutor` builds scoped component groups and emits `Build Report` artifacts
7. System Validators emit `Validation Result Bundle` artifacts
8. `Inspeqtor` emits `Inspection Verdict`
9. Orchestrator marks run finished or repairable
10. If repair is required, only targeted scopes re-enter build and validation
11. Run manifest and audit remain authoritative across the full run

### Current compatibility flow

- Runtime currently operates through `worqspace/qage_*`
- `qrane.py` executes YAML-defined stage order
- `tasqleveler` may rewrite cycle-1 task
- `instruqtor` generates briqs and current QONTRACT artifacts
- `construqtor` writes directly into `qodeyard/`
- warmup helpers run from seeded code:
  - `qompressor`
  - `qontextor`
  - `qontrabender`
- `inspeqtor` writes `reqap.d/cyqleN_reqap.md`
- checkpoint logic may promote `reqap` into next-cycle `tasq`

### Bridge flow references

- `Qrystallizer` becomes the canonical front door while compatibility flows may still feed planning through current task files
- guard result is introduced before planning even if deterministic enforcement continues later
- planning package becomes canonical execution truth even while current briq/file contracts still exist
- `reqap` becomes readable review output, but targeted repair and continuation metadata become canonical continuation truth
- qage-local artifacts may be mirrored or indexed into `.qonqrete` manifest-linked state during migration
- support artifacts remain auxiliary and must not replace manifest-indexed contract truth

### Gates and checkpoints

Required gates:
- readiness gate before planning
- guard/policy gate before build
- optional estimate/user gate before build
- optional estimate/user gate before repair
- validator evidence gate before inspection verdict
- repair-cap gate after bounded repair attempts
- continuation gate before resuming from prior run state

### Repair-pass flow

- repair is scoped by `Inspection Verdict` targets
- repair reuses locked planning package unless an explicit repair-plan update exists
- repair must not reopen user questioning
- repair must not silently become a full autonomous rerun loop
- repair artifacts append to the same run manifest lineage or a linked continuation record
- repair passes are capped and visible in audit

## Responsibility Separation

### AI

AI owns:
- clarification reasoning
- planning synthesis
- scoped implementation generation
- evidence-based completion judgment

AI does not own:
- orchestration
- stage gating
- manifest lifecycle
- mechanical proof
- sandbox execution policy
- final runtime control

### Deterministic system

Deterministic system owns:
- stage sequencing
- policy enforcement boundaries
- artifact presence checks
- persistence wiring
- manifest creation and updates
- repair-cap enforcement
- continuation routing
- capability-mode disclosure

### Validators

Validators own:
- syntax/parsing checks
- import/interface/schema checks
- deterministic contract/policy checks where implemented
- grouped component coherence checks
- sandboxed test execution when enabled
- machine-readable evidence bundles

### Audit/logging

Audit/logging owns:
- high-level timeline
- deep technical trace
- assumption records
- fallback records
- degraded-mode disclosure
- event linkage across all stages
- manifest cross-reference integrity

### Orchestration

Orchestration owns:
- run identity
- lifecycle transitions
- stage preconditions
- handoff integrity
- verdict routing to finish vs repair
- continuation metadata and resumption behavior

## Validation Ownership Matrix

| Validation Area | Primary Owner | Supporting Owner | Validation Nature |
| --- | --- | --- | --- |
| Syntax / parseability | System Validators | Orchestrator for gating | deterministic |
| Imports / interface / schema checks | System Validators | Planning artifacts define expected interfaces | deterministic |
| Required artifact presence | Orchestrator / Runtime Authority | System Validators may reference | deterministic |
| Policy / pre-build guard | Guard / Policy Validation Stage | Deterministic contract enforcement later | deterministic |
| Contract conformance | System Validators | `Inspeqtor` interprets residual gaps | deterministic first, interpretive second |
| Grouped component coherence | System Validators | `Constrqutor` provides build scope artifacts | deterministic where supported |
| Test execution | System Validators / controlled execution layer | Orchestrator enforces sandbox boundary | executed |
| Architecture alignment | `Inspeqtor` | Validators provide evidence where possible | interpretive with evidence |
| Completion criteria evaluation | `Inspeqtor` | Validators and build reports supply evidence | interpretive with evidence |
| Final verdict | `Inspeqtor` | Orchestrator persists lifecycle result | interpretive with evidence |
| Repair target selection | `Inspeqtor` | Orchestrator enforces repair cap/scope routing | interpretive with evidence |
| Continuation eligibility | Orchestrator / Runtime Authority | `Inspeqtor` verdict and manifest status inform | deterministic plus policy |

## Execution Boundaries

Stage boundaries:
- `Qrystallizer` may read task input and approved context, but may not mutate repo code
- Guard stage may validate clarified task and emit constraints, but may not generate architecture or code
- `Instruqtor` may synthesize planning artifacts, but may not mutate repo code or declare completion
- `Constrqutor` may mutate repo code only within scoped component/group boundaries
- System Validators may execute only approved validation/test actions within sandbox boundaries
- `Inspeqtor` may judge and target repairs only after validator evidence exists
- Orchestrator may create/update manifests and continuation metadata, but may not outsource orchestration decisions to AI

Execution rules:
- No stage after `Qrystallizer` may ask the user anything
- Any mid-run model question is a failure condition to be retried or converted into a logged assumption by system policy
- No hidden decision-making after readiness
- No architecture rewriting by builders
- No planner authority in validators
- No execution authority in `Inspeqtor`
- No silent degraded mode
- No silent contract mutation
- No claim of mechanical correctness without deterministic or executed evidence
- Simulation mode and execution mode must be explicitly disclosed in artifacts and audit

## Repo / File Contracts

Current-state artifact roots:
- persistent workspace inputs under `worqspace/`
- per-run state under `worqspace/qage_*`
- saved snapshots under `worqspace/qonstructions/`

Target-state persistence contract:
- repo-native state under `.qonqrete/`
- stable artifact hierarchy by run and component/group
- continuation metadata and run manifest as first-class state
- support/context/cache artifacts placed under manifest-linked support paths, not as hidden authorities

Artifact ownership and placement:
- task intake and clarified task under `.qonqrete/runs/<run_id>/artifacts/task/`
- guard results under `.qonqrete/runs/<run_id>/artifacts/guard/`
- planning package under `.qonqrete/runs/<run_id>/artifacts/plan/`
- build reports under `.qonqrete/runs/<run_id>/artifacts/build/`
- validator bundles under `.qonqrete/runs/<run_id>/artifacts/validation/`
- verdicts under `.qonqrete/runs/<run_id>/artifacts/verdict/`
- audit timeline and deep trace under `.qonqrete/runs/<run_id>/artifacts/audit/`
- continuation state under `.qonqrete/runs/<run_id>/artifacts/continuation/`
- run manifest at `.qonqrete/runs/<run_id>/run-manifest.*`

Manifest linkage rules:
- every major artifact must be reachable from the run manifest
- support/cache artifacts may exist outside core artifact paths, but must be indexed by manifest if they matter to the run
- audit entries must reference stage identity and artifact identity
- continuation metadata must point back to source run and inherited artifacts

Persistence boundaries:
- repo code remains the source of truth for code
- task files supplied by the user remain source artifacts, not rewritten planning truth
- QonQrete-managed state is the source of truth for run reasoning, constraints, evidence, and verdicts
- support caches and context artifacts must not become hidden planning authorities
- compatibility-era qage artifacts may coexist temporarily, but `.qonqrete` is the canonical target persistence model

## Inconsistencies or Open Structural Risks

- Current pipeline order has a verified mismatch between comment-described order and actual configured order in `worqspace/pipeline_config.yaml`
- `qrane/paths.py` defines `qache_dir` under `sqrapyard/qache.d`, while runtime descriptions and pipeline config treat `qache.d/` as a qage/run artifact
- Historical `Qrystallizer/Qualifier` artifacts in `worqspace/qage_20260402_172204/` conflict with both current implemented reality and target no-Qualifier contract; they must remain non-canonical
- Current runtime still relies on cycle promotion semantics and qage-local state, while target contract is single-pass plus targeted repair with `.qonqrete/` state
- Deterministic validation remains strongest for Python-centric flows; Qonscience therefore forbids claiming uniform mechanical validation coverage where that does not yet exist
- `calqulator` currently mutates briq files, which conflicts with the cleaner target notion of estimation as manifest/planning metadata
- `construqtor` currently writes incrementally into `qodeyard/` without transactional rollback, so partial-state risks remain in current reality
- current auditability is real but fragmented; until the run manifest becomes authoritative, artifact linkage remains more fragile than the target contract requires
- support helpers such as `qontextor`, `qompressor`, and `qontrabender` risk becoming hidden authorities if their outputs are treated as plan truth rather than auxiliary support state
- during migration, qage-local file contracts and manifest-linked target contracts may drift if both are not explicitly linked and versioned in the same run truth chain
