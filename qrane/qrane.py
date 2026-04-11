#!/usr/bin/env python3
# qrane/qrane.py - QonQrete Qrane orchestrator
import argparse
import logging
import os
import subprocess
import sys
import time
import traceback
import select
from pathlib import Path
import yaml
import re
import shutil
import json

# Add script's directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from loader import Spinner, Colors
    from paths import PathManager
except ImportError:
    Spinner = None; Colors = None; PathManager = None

try:
    from manifest_bridge import (
        STAGE_ALIAS_MAP,
        append_audit_event,
        complete_stage,
        create_manifest,
        finalize_manifest,
        load_manifest,
        record_agent_completion,
        record_cycle_promotion,
        record_support_service,
        save_manifest,
        start_stage,
        sync_artifact_slots,
    )
except ImportError:
    STAGE_ALIAS_MAP = {}
    append_audit_event = None
    complete_stage = None
    create_manifest = None
    finalize_manifest = None
    load_manifest = None
    record_agent_completion = None
    record_cycle_promotion = None
    record_support_service = None
    save_manifest = None
    start_stage = None
    sync_artifact_slots = None

try:
    import tui
except ImportError:
    tui = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODULE_DIR = PROJECT_ROOT / "worqer"

class KillSignal(Exception): pass


def get_agent_config(agent_configs: dict, agent_name: str) -> dict:
    if agent_name in agent_configs:
        return agent_configs.get(agent_name, {})
    if agent_name == "qrystallizer":
        return agent_configs.get("tasqleveler", {})
    if agent_name == "tasqleveler":
        return agent_configs.get("qrystallizer", {})
    return {}

def get_version():
    suffix = "-beta"
    v = os.environ.get("QONQ_VERSION")
    if v:
        clean_v = v.replace("v", "")
        return f"QonQrete v{clean_v}{suffix}"
    try:
        v_file = PROJECT_ROOT / "VERSION"
        if v_file.exists():
            with open(v_file, "r") as f:
                clean_v = f.read().strip().replace("v", "")
                return f"QonQrete v{clean_v}{suffix}"
    except: pass
    return f"QonQrete v?.?.?{suffix}"

def get_worqspace() -> Path:
    env_path = os.environ.get("QONQ_WORKSPACE")
    return Path(env_path) if env_path else PROJECT_ROOT / "worqspace"

def check_tui_keys(ui, proc=None):
    key = ui.get_key_nonblocking()
    if key == -1: return
    if key == 32: ui.toggle_qonsole()
    elif key == ord('w') or key == ord('W'): ui.toggle_wonqrete()
    elif key == 27:
        if proc: proc.terminate()
        raise KeyboardInterrupt
    elif key == ord('k') or key == ord('K'):
        if proc: proc.kill()
        raise KillSignal

def run_agent(agent_name: str, command: list[str], prefix: str, color: str, logger: logging.Logger, qonsole_log_path: Path, events_log_path: Path, env: dict, ui=None) -> bool:
    # Display name overrides
    DISPLAY_NAME_OVERRIDES = {
        'loqal_verifier': 'inspeQtor',  # LoQal verifier is part of InspeQtor pipeline
    }
    
    if agent_name in DISPLAY_NAME_OVERRIDES:
        agent_display_name = DISPLAY_NAME_OVERRIDES[agent_name]
    else:
        agent_display_name = agent_name.replace('q', 'Q')
    
    target_width = 11
    padding = " " * (target_width - len(agent_display_name))
    qrane_padding = " " * (target_width - 5)

    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"
    agent_prefix = f"{Colors.B}〘{prefix}〙『{color}{agent_display_name}{Colors.B}』{padding}⸎ {Colors.R}"

    # ═══════════════════════════════════════════════════════════════════════════════
    # DISPLAY FILTER SYSTEM v0.8.8 - Fixed to show all status messages
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Keywords that SHOULD be displayed (high-level status only)
    # These are checked FIRST - if a line contains ANY of these, it displays
    VISIBLE_KEYWORDS = [
        # TasqLeveler status (v0.9.0+) - only key status lines
        "[TasqLeveler]",
        "[Qrystallizer]",
        "[Guard]",
        
        # ConstruQtor status - explicit patterns
        "--- ConstruQtor", "-- Processing Briq:", "- Wrote [Code]", "- Wrote [Plan]",
        "-- Briq Complete:", "Wrote exeQ:", "Per-briq exeQ",
        "attempts:", "[SUCCESS]", "[FAILURE]", "[PARTIAL]",
        "[SKIP]", "[WARN]", "[ERROR]",
        
        # LoQal Verifier (runs during build AND inspeQtor)
        "[LoQal]",
        
        # InstruQtor status
        "--- Architect", "Generating", "Ingesting", "Estimated cost:",
        
        # InspeQtor status - ONLY final assessment (v0.9.8+)
        "=== InspeQtor", "=== Final Assessment:",
        
        # CalQulator status
        "CalQulator", "Est. Cost", "TOTAL CYCLE", "-----------------------------------",
        
        # Qontextor/Qompressor/Qontrabender
        "--- Qontrabender", "Pipeline mode", "Payload", "Qache", "Fidelity",
        "Skeletonizing", "--- Dependencies", "Initial scan", "Update scan", "DISABLED",
        
        # Generic status
        "Handing off", "Executed", "Complete:", "reQap", "exeQ",
    ]
    
    # Keywords that should NEVER be displayed (suppress AI output noise)
    BLOCKED_KEYWORDS = [
        # TasqLeveler verbose output (v0.9.8+)
        "## 📋", "## 📦", "## 🎯", "## 🧪", "## ⏱️",
        "# 🎯 Golden Path", "Overview", "Dependency Graph", "Success Criteria",
        "Mock Infrastructure", "TOKEN BUDGET", "CONFIGURATION",
        
        # InspeQtor verbose review content
        "## Summary", "## Issues Found", "## Suggestions", "## Executive",
        "## Critical Issues", "## Integration", "## Per-Briq", "## Warning",
        "## Consolidated", "## Patterns", "| Briq |", "| briq",
        "-- Reviewing:",  # Individual briq review headers
        "Assessment: SUCCESS", "Assessment: PARTIAL", "Assessment: FAILURE",
        "Assessment: [SUCCESS]", "Assessment: [PARTIAL]", "Assessment: [FAILURE]",
        
        # InspeQtor table dividers (v0.9.8+)
        "|----", "|---", "|-", "| ---",
        
        # InspeQtor batch/review noise (v0.9.8+)
        "-- Batch ", "Batch results:", "--- Reviews complete:",
        "Estimated batch cost:", "[CROSS-BRIQ]",
        
        # Code snippets
        "except ", "try:", "raise ", "return ", "import ", "from ",
        "def ", "class ", "elif ", "else:", "while ",
        "async ", "await ", "as e:", "lambda ", "yield ",
        "self.", "logger.", "print(", "logging.", "pytest.",
        
        # Code exceptions
        "FileNotFoundError", "TypeError", "ValueError",
        "KeyError", "AttributeError", "IndexError", "RuntimeError",
        
        # Markdown noise
        "```", "- **", "* **", "### ",
    ]
    
    # Patterns that indicate code content (for lines WITHOUT visible keywords)
    CONTENT_FILTER_PATTERNS = [
        # Markdown headers and formatting (v0.9.9+)
        "## ", "# 🎯", "# 📋", "# 📦", "# 🧪", "# ⏱️",
        "|---", "|-", "| ---",  # Table dividers
        
        # Code patterns
        "let ", "var ", "const ", "function ", "module.exports",
        "require(", "struct ", "enum ", "impl ", "fn ", "pub ",
        "self.", "this.", "super.",
        "<html", "<head", "<body", "<div", "<script",
        '{"', "{'", '": {',
        "});", ");", "};", "=> {",
        "console.", "fmt.", "println",
    ]
    
    def should_display(line: str) -> bool:
        """Determine if a line should be displayed in the event log."""
        # PRIORITY 1: Check for visible keywords FIRST - these always display
        for kw in VISIBLE_KEYWORDS:
            if kw in line:
                # But still block if it's clearly AI review noise
                if any(blocked in line for blocked in BLOCKED_KEYWORDS):
                    return False
                return True
        
        # PRIORITY 2: No visible keyword - filter out code/content
        # Very long lines are content
        if len(line) > 300:
            return False
        
        # Check for content patterns
        for pattern in CONTENT_FILTER_PATTERNS:
            if pattern in line:
                return False
        
        # Lines starting with code constructs
        stripped = line.lstrip()
        code_starters = ('let ', 'var ', 'const ', 'def ', 'class ', 'function ', 
                         'import ', 'from ', 'return ', 'if ', 'for ', 'while ',
                         'pub ', 'fn ', 'use ', 'mod ', 'struct ', 'enum ', 
                         '//', '/*', '#!', '<?', '<!', '<html',
                         'self.', 'this.', 'super.', 'except ', 'try:', 'raise ')
        if any(stripped.lower().startswith(s.lower()) for s in code_starters):
            return False
        
        # Default: don't display unrecognized lines
        return False

    def iter_ready_lines(proc, reads, buffers):
        readable, _, _ = select.select(reads, [], [], 0.05)
        yielded = False
        for stream in list(readable):
            chunk = stream.read(1)
            if chunk == "":
                remainder = buffers.pop(stream, "")
                if remainder:
                    yielded = True
                    yield stream, remainder
                reads.remove(stream)
                continue
            buffers[stream] = buffers.get(stream, "") + chunk
            while "\n" in buffers[stream]:
                line, remainder = buffers[stream].split("\n", 1)
                buffers[stream] = remainder
                yielded = True
                yield stream, line + "\n"
        if not yielded and proc.poll() is not None:
            for stream in list(reads):
                remainder = buffers.pop(stream, "")
                if remainder:
                    yield stream, remainder
                reads.remove(stream)

    event_start_msg = f"Initiating {agent_display_name}..."
    with open(events_log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {event_start_msg}\n")

    if ui:
        ui.log_main(f"{qrane_prefix}{event_start_msg}")
        try:
            with subprocess.Popen(command, cwd=str(get_worqspace()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=env, universal_newlines=True) as proc, \
                 open(qonsole_log_path, 'a', encoding='utf-8') as qonsole_log:

                reads = [proc.stdout, proc.stderr]
                stream_buffers = {proc.stdout: "", proc.stderr: ""}
                while True:
                    check_tui_keys(ui, proc)
                    for r, line in iter_ready_lines(proc, reads, stream_buffers):
                        qonsole_log.write(line)

                        clean = line.strip()
                        if r == proc.stdout:
                            if should_display(clean):
                                ui.log_main(f"{agent_prefix} {clean}")
                            ui.log_agent(f"[{agent_display_name}] {clean}")
                        elif r == proc.stderr:
                            ui.log_agent(f"[{agent_display_name} RAW] {clean}")

                    if proc.poll() is not None and not reads: break

                if proc.returncode != 0:
                    event_fail_msg = f"Agent {agent_display_name} FAILED (Code {proc.returncode})"
                    with open(events_log_path, 'a', encoding='utf-8') as f:
                        f.write(f"[{time.strftime('%H:%M:%S')}] {event_fail_msg}\n")
                    ui.log_main(f"{agent_prefix}FAILED (Code {proc.returncode})")
                    return False

                event_ok_msg = f"Agent {agent_display_name} finished successfully."
                with open(events_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {event_ok_msg}\n")
                return True
        except KillSignal: raise
        except Exception as e:
            ui.log_main(f"CRITICAL EXCEPTION: {e}")
            return False
    else:
        print(f"{qrane_prefix}{event_start_msg}")
        spinner = Spinner(prefix=f"〘{prefix}〙", message=f"Running {agent_display_name}...")
        spinner.start()
        try:
            stderr_capture = []
            with subprocess.Popen(command, cwd=str(get_worqspace()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1, universal_newlines=True) as proc, \
                 open(qonsole_log_path, 'a', encoding='utf-8') as qonsole_log:

                reads = [proc.stdout, proc.stderr]
                stream_buffers = {proc.stdout: "", proc.stderr: ""}
                while True:
                    any_output = False
                    for r, line in iter_ready_lines(proc, reads, stream_buffers):
                        any_output = True
                        qonsole_log.write(line)

                        if r == proc.stderr:
                            stderr_capture.append(line)

                        clean = line.strip()
                        # For the calqulator, print all output to show the table.
                        # For other agents, only print lines with important keywords (excluding content).
                        if agent_name == "calqulator" or should_display(clean):
                            spinner.stop()
                            print(f"{agent_prefix}{clean}")
                            spinner.start()
                    if not any_output and proc.poll() is not None and not reads:
                        break

            spinner.stop()

            if proc.returncode != 0:
                event_fail_msg = f"Agent {agent_display_name} FAILED (Code {proc.returncode})"
                with open(events_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {event_fail_msg}\n")

                print(f"{agent_prefix}{Colors.RED}ERROR: Agent exited with code: {proc.returncode}{Colors.R}")

                stderr_output = "".join(stderr_capture)
                if stderr_output:
                    print(f"{Colors.RED}--- STDERR DUMP ---{Colors.R}")
                    for line in stderr_output.strip().split('\n'):
                        print(f"{Colors.RED}{line}{Colors.R}")
                return False

            event_ok_msg = f"Agent {agent_display_name} finished successfully."
            with open(events_log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {event_ok_msg}\n")
            return True
        except KillSignal:
            spinner.stop()
            raise
        except KeyboardInterrupt:
            spinner.stop()
            try: proc.kill()
            except: pass
            raise
        except Exception as e:
            spinner.stop()
            print(f"{Colors.RED}Critical Error: {e}{Colors.R}")
            traceback.print_exc()
            return False

def load_task_spec_status(workspace_root: Path) -> tuple[bool | None, str | None]:
    task_spec_path = workspace_root / "task" / "task-spec.v1.json"
    if not task_spec_path.exists():
        return None, None
    try:
        payload = json.loads(task_spec_path.read_text(encoding="utf-8"))
        return payload.get("ready"), payload.get("status")
    except Exception:
        return None, None


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def repair_plan_path(workspace_root: Path) -> Path:
    return workspace_root / "verdict" / "repair-plan.v1.json"


def inspection_verdict_path(workspace_root: Path) -> Path:
    return workspace_root / "verdict" / "inspection-verdict.v1.json"


def continuation_metadata_path(workspace_root: Path) -> Path:
    return workspace_root / "continuation" / "continuation-metadata.v1.json"


def load_inspection_artifacts(workspace_root: Path) -> tuple[dict, dict]:
    return (
        load_optional_json(inspection_verdict_path(workspace_root)),
        load_optional_json(repair_plan_path(workspace_root)),
    )


def get_repair_config(config: dict | None = None) -> dict:
    repair_cfg = (config or {}).get("repair", {})
    return {
        "max_attempts": max(0, int(repair_cfg.get("max_attempts", 1))),
    }


def _rename_briq_for_cycle(source_name: str, target_cycle: int) -> str:
    return re.sub(r"^cyqle\d+_", f"cyqle{target_cycle}_", source_name)


def prepare_same_run_repair_cycle(
    current_cycle: int,
    target_cycle: int,
    prefix: str,
    path_manager: PathManager,
    repair_plan: dict,
    ui=None,
) -> bool:
    target_briqs = repair_plan.get("target_briq_files", [])
    if not target_briqs:
        return False

    target_tasq_path = path_manager.get_tasq_path(target_cycle)
    target_tasq_path.parent.mkdir(parents=True, exist_ok=True)
    target_tasq_path.write_text(
        "\n".join([
            f"# Cycle {target_cycle} Repair Directive",
            "",
            f"Source cycle: {current_cycle}",
            f"Repair pass index: {repair_plan.get('repair_pass_index')}",
            f"Reason: {repair_plan.get('repair_reason_summary', 'Bounded targeted repair required.')}",
            "",
            "Target build groups:",
            *[f"- {item}" for item in repair_plan.get("target_build_groups", [])],
            "",
            "Target briqs:",
            *[f"- {item}" for item in target_briqs],
            "",
            "Required actions:",
            *[f"- {item}" for item in repair_plan.get("required_actions", [])],
            "",
            "This cycle is an explicit repair wrapper. It is not canonical reqap promotion.",
            "",
        ]),
        encoding="utf-8",
    )

    briq_dir = path_manager.get_briq_dir()
    created_files = []
    for briq_ref in target_briqs:
        source_path = briq_dir / briq_ref
        if not source_path.exists():
            continue
        target_name = _rename_briq_for_cycle(source_path.name, target_cycle)
        target_path = briq_dir / target_name
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except Exception:
            continue
        repair_block = "\n".join([
            "",
            "## Explicit Repair Context",
            f"- Repair pass index: {repair_plan.get('repair_pass_index')}",
            f"- Repair reason: {repair_plan.get('repair_reason_summary', 'Bounded targeted repair required.')}",
            "- This briq is being re-executed as an explicit targeted repair pass.",
            "- Address the required actions and evidence-linked issues below before making new changes.",
            "",
            "### Required Actions",
            *[f"- {item}" for item in repair_plan.get("required_actions", [])],
            "",
            "### Evidence References",
            *[f"- {item}" for item in repair_plan.get("evidence_refs", [])],
            "",
            "### Repair Constraints",
            *[f"- {item}" for item in repair_plan.get("repair_constraints", [])],
            "",
        ])
        target_path.write_text(source_text.rstrip() + "\n" + repair_block, encoding="utf-8")
        created_files.append(str(target_path.relative_to(path_manager.root)))

    if not created_files:
        return False

    if append_audit_event:
        append_audit_event(
            path_manager.root,
            "repair_cycle_prepared",
            "REPAIR",
            "same_run_targeted_repair",
            "Prepared explicit same-run targeted repair cycle from repair plan.",
            {
                "source_cycle": current_cycle,
                "target_cycle": target_cycle,
                "repair_plan_ref": "verdict/repair-plan.v1.json",
                "target_briqs": target_briqs,
                "created_briq_files": created_files,
            },
        )

    if sync_artifact_slots:
        sync_artifact_slots(path_manager.root)

    target_width = 11
    qrane_padding = " " * (target_width - 5)
    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"
    msg = (
        f"Prepared same-run targeted repair cycle {target_cycle} with "
        f"{len(created_files)} scoped briq copies from repair plan."
    )
    if ui:
        ui.log_main(f"{qrane_prefix}{msg}")
    else:
        print(f"{qrane_prefix}{msg}")
    return True


def write_continuation_metadata(
    workspace_root: Path,
    repair_plan: dict,
    reason: str,
    next_run_id: str | None = None,
) -> str:
    continuation_path = continuation_metadata_path(workspace_root)
    continuation_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("QONQ_LEGACY_QAGE_ID") or workspace_root.name
    payload = {
        "schema_version": "continuation-metadata.v1",
        "continuation_id": f"{run_id}-continuation",
        "source_run_id": run_id,
        "resume_point": repair_plan.get("next_lifecycle_transition", "CONTINUABLE"),
        "planning_reuse_mode": repair_plan.get("planning_reuse_mode", "reuse_locked_plan"),
        "continuation_reason": reason,
        "next_run_id": next_run_id,
        "repair_plan_ref": "verdict/repair-plan.v1.json",
        "evidence_refs": repair_plan.get("evidence_refs", []),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    continuation_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(continuation_path.relative_to(workspace_root))


def update_manifest_for_repair_state(
    workspace_root: Path,
    lifecycle_state: str,
    run_status: str,
    detail: str,
    continuation_artifact: str | None = None,
) -> None:
    if not load_manifest or not save_manifest:
        return
    if sync_artifact_slots:
        sync_artifact_slots(workspace_root)
    manifest = load_manifest(workspace_root)
    manifest["lifecycle_state"] = lifecycle_state
    manifest["run_status"] = run_status
    manifest["compatibility"]["continuation_model"] = "EXPLICIT_REPAIR_PLAN_CANONICAL"
    if continuation_artifact:
        manifest.setdefault("artifacts", {})["continuation_metadata"] = continuation_artifact
    save_manifest(workspace_root, manifest)
    if append_audit_event:
        append_audit_event(
            workspace_root,
            "repair_state_updated",
            "REPAIR",
            "explicit_repair_flow",
            detail,
            {
                "lifecycle_state": lifecycle_state,
                "run_status": run_status,
                "continuation_metadata": continuation_artifact,
            },
        )


def legacy_cycle_continuation_enabled(config: dict | None = None) -> bool:
    env_value = os.environ.get("QONQ_ENABLE_LEGACY_CONTINUATION", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    return bool((config or {}).get("options", {}).get("legacy_cycle_continuation", False))


def handle_cheqpoint(
    cycle: int,
    is_autonomous: bool,
    reqap_path: Path,
    prefix: str,
    path_manager: PathManager,
    ui=None,
    no_midrun_questions: bool = False,
    legacy_continuation: bool = False,
    config: dict | None = None,
    repair_attempts_started: int = 0,
) -> str:
    target_width = 11
    gatekeeper_name = "gateQeeper"
    p_padding = " " * (target_width - len(gatekeeper_name))
    gate_prefix = f"{Colors.B}〘{prefix}〙『{Colors.YELLOW}{gatekeeper_name}{Colors.B}』{p_padding}⸎ {Colors.R}"

    assessment = "Unknown"
    content = ""
    inspection_verdict, repair_plan = load_inspection_artifacts(path_manager.root)
    repair_required = bool(inspection_verdict.get("repair_required"))
    repair_config = get_repair_config(config)
    try:
        if reqap_path.exists():
            with open(reqap_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r"Assessment:.*?(SUCCESS|PARTIAL|FAILURE)", content, re.IGNORECASE | re.DOTALL)
            if match:
                assessment = match.group(1).strip()
        else:
            content = f"[ERROR] reQap not found at {reqap_path}"
    except Exception as e:
        content = f"[ERROR] Could not read reQap: {e}"

    if inspection_verdict.get("status"):
        assessment = inspection_verdict["status"]

    if repair_required and repair_plan:
        same_run_eligible = bool(repair_plan.get("same_run_repair_eligible"))
        repair_cap_remaining = repair_attempts_started < repair_config["max_attempts"]
        if same_run_eligible and repair_cap_remaining:
            should_repair_now = is_autonomous or no_midrun_questions
            if not should_repair_now:
                if ui:
                    ui.log_main(f"{gate_prefix}Repair plan available. [R]epair now, [L]ink later, [X]Quit")
                    choice = ui.get_input_blocking(f"{gate_prefix}Selection").lower()
                else:
                    print("\n" + f"{Colors.YELLOW}=== Repair Gate {cycle:03d} ==={Colors.R}")
                    print(content)
                    print(f"{gate_prefix}Repair plan available. [R]epair now, [L]ink later, [X]Quit")
                    sys.stdout.write(f"{gate_prefix}Selection: {Colors.R}")
                    sys.stdout.flush()
                    choice = getch().lower()
                    if choice in ['\r', '\n']:
                        choice = 'x'
                    print(choice)
                if choice == 'r':
                    should_repair_now = True
                elif choice == 'l':
                    continuation_artifact = write_continuation_metadata(
                        path_manager.root,
                        repair_plan,
                        repair_plan.get("repair_reason_summary", "Deferred bounded repair continuation."),
                    )
                    update_manifest_for_repair_state(
                        path_manager.root,
                        "CONTINUABLE",
                        "RUN_REPAIR_PENDING",
                        "Deferred repair as explicit linked continuation.",
                        continuation_artifact,
                    )
                    return 'STOP_PARTIAL'
                else:
                    return 'QUIT'

            if should_repair_now:
                if prepare_same_run_repair_cycle(cycle, cycle + 1, prefix, path_manager, repair_plan, ui=ui):
                    update_manifest_for_repair_state(
                        path_manager.root,
                        "REPAIRING",
                        "RUN_ACTIVE",
                        "Approved same-run targeted repair from manifest-linked repair plan.",
                    )
                    return 'REPAIR'

        continuation_artifact = write_continuation_metadata(
            path_manager.root,
            repair_plan,
            repair_plan.get("repair_reason_summary", "Repair requires later linked continuation."),
        )
        update_manifest_for_repair_state(
            path_manager.root,
            "CONTINUABLE",
            "RUN_REPAIR_PENDING",
            "Repair remains explicit and deferred to a later linked run.",
            continuation_artifact,
        )
        if legacy_continuation and not no_midrun_questions:
            msg = "Repair is canonical. Legacy reqap promotion remains opt-in compatibility only."
            if ui:
                ui.log_main(f"{gate_prefix}{msg}")
            else:
                print(f"{gate_prefix}{msg}")
        return 'STOP_PARTIAL'

    if no_midrun_questions and not legacy_continuation:
        msg = (
            "Bounded clarified run complete. Legacy reqap -> next tasq continuation is disabled "
            "unless explicitly re-enabled via compatibility mode."
        )
        if ui:
            ui.log_main(f"{gate_prefix}{msg}")
        else:
            print(f"{gate_prefix}{msg}")
        return 'STOP'

    if not legacy_continuation:
        msg = (
            "Canonical inspection completed without repair. Legacy reqap -> next tasq continuation "
            "is disabled unless explicitly re-enabled via compatibility mode."
        )
        if ui:
            ui.log_main(f"{gate_prefix}{msg}")
        else:
            print(f"{gate_prefix}{msg}")
        return 'STOP'

    if is_autonomous:
        msg = "Autonomous Mode: Qontinuing..."
        if ui: ui.log_main(f"{gate_prefix}{msg}")
        else:
            print("\n" + f"{Colors.YELLOW}=== Cheqpoint {cycle:03d} ==={Colors.R}")
            print(content)
            print(f"{gate_prefix}{msg}")
        promote_reqap(cycle, prefix, path_manager, ui=ui)
        return 'QONTINUE'

    if no_midrun_questions:
        msg = (
            "No-mid-run-question enforcement active after readiness acceptance. "
            "Ending without prompting or implicit continuation."
        )
        if ui:
            ui.log_main(f"{gate_prefix}{msg}")
        else:
            print(f"{gate_prefix}{msg}")
        return 'STOP'

    while True:
        if ui:
            ui.log_main(f"--- reQap Cycle {cycle} ---")
            ui.log_main(f"{gate_prefix}Result: {assessment}")
            prompt = f"{gate_prefix}[Q]ontinue, [T]weaQ (Edit), [X]Quit"
            choice = ui.get_input_blocking(prompt).lower()
        else:
            print("\n" + f"{Colors.YELLOW}=== Cheqpoint {cycle:03d} ==={Colors.R}")
            print(content)
            print(f"{Colors.YELLOW}==========================={Colors.R}")
            print(f"{gate_prefix}Result: {Colors.WHITE}{assessment}{Colors.R}")
            print(f"{gate_prefix}[Q]ontinue, [T]weaQ (Edit), [X]Quit")
            sys.stdout.write(f"{gate_prefix}Selection: {Colors.R}")
            sys.stdout.flush()
            choice = getch().lower()
            if choice in ['\r', '\n']: continue
            print(choice)

        if choice == 'q':
            msg = "gateQeeper's reQap imported..."
            if ui: ui.log_main(f"{gate_prefix}{msg}")
            else: print(f"{gate_prefix}{msg}")
            promote_reqap(cycle, prefix, path_manager, ui=ui)
            return 'QONTINUE'
        elif choice == 'x': return 'QUIT'
        elif choice == 't':
            editor = os.environ.get('EDITOR', 'vim')
            if ui: ui.suspend_and_run([editor, str(reqap_path)])
            else: subprocess.call([editor, str(reqap_path)])
            try:
                with open(reqap_path, 'r', encoding='utf-8') as f: content = f.read()
            except: pass
            continue

def promote_reqap(cycle: int, prefix: str, path_manager: PathManager, ui=None):
    src = path_manager.get_reqap_path(cycle)
    dst = path_manager.get_tasq_path(cycle + 1)

    target_width = 11
    qrane_padding = " " * (target_width - 5)
    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"

    if src.exists():
        os.makedirs(dst.parent, exist_ok=True)
        with open(src, 'r') as f: content = f.read()

        assessment_status = "Unknown"
        match = re.search(r"Assessment:.*?(SUCCESS|PARTIAL|FAILURE)", content, re.IGNORECASE | re.DOTALL)
        if match:
            assessment_status = match.group(1).strip()

        header = f"# Cycle {cycle+1} Directive\n\n**PREVIOUS CYCLE STATUS:** {assessment_status}\n\n**CRITICAL INSTRUCTION:**\n1. Analyze Assessment.\n2. Fix failures if Partial/Failure.\n3. Implement suggestions if Success.\n\n---\n\n"
        with open(dst, 'w') as f: f.write(header + content)

        msg = f"Successfully created {dst.name}."
        if ui: ui.log_main(f"{qrane_prefix}{msg}")
        else: print(f"{qrane_prefix}{msg}")
        if record_cycle_promotion:
            record_cycle_promotion(path_manager.root, cycle, str(dst.relative_to(path_manager.root)))

def getch():
    try:
        import tty, termios
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        try: tty.setraw(fd); return sys.stdin.read(1)
        finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except: return sys.stdin.read(1)

def check_api_keys(config, qrane_prefix):
    providers = set()
    for agent_config in config.get('agents', {}).values():
        if 'provider' in agent_config:
            providers.add(agent_config['provider'].lower())

    if not providers:
        return

    key_mapping = {
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'deepseek': 'DEEPSEEK_API_KEY',
        'qwen': 'QWEN_API_KEY',
        'openrouter': 'OPENROUTER_API_KEY'
    }

    missing_keys = []
    for provider in providers:
        if provider in ('gemini', 'google'):
            if not (os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')):
                missing_keys.append('GOOGLE_API_KEY/GEMINI_API_KEY')
        elif provider in key_mapping:
            key_name = key_mapping[provider]
            if not os.environ.get(key_name):
                missing_keys.append(key_name)

    if missing_keys:
        print(f"{qrane_prefix}[ERROR] API Keys missing. Ensure the following environment variables are set for the providers listed in your config.yaml: {', '.join(missing_keys)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(prog="QonQrete")
    parser.add_argument("-a", "--auto", action="store_true", help="Autonomous Mode")
    parser.add_argument("-u", "--user", action="store_true", help="Force User-gated Mode")
    parser.add_argument("-t", "--tui", action="store_true", help="Enable TUI")
    parser.add_argument("-w", "--wonqrete", action="store_true", help="Exp Mode")
    parser.add_argument("-V", "--version", action="version", version=get_version())
    parser.add_argument("-m", "--mode", type=str, help="Operational Mode (program, enterprise, etc)")
    parser.add_argument("-b", "--briq-sensitivity", type=int, help="Granularity (0-9)")
    parser.add_argument("-c", "--cyqles", type=int, help="Max auto-cycles (1-50)")
    args = parser.parse_args()

    if args.auto and args.user:
        sys.stderr.write("Error: --auto and --user flags are mutually exclusive.\\n")
        sys.exit(1)

    worqspace = get_worqspace()
    try:
        with open(worqspace / 'config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    cheqpoint_config = config.get('options', {}).get('cheqpoint', True)

    if args.user:
        is_autonomous = False
    elif args.auto:
        is_autonomous = True
    else:
        is_autonomous = not cheqpoint_config

    prefix = "aQQ" if is_autonomous else "uQQ"
    if args.wonqrete: prefix = "aWQ" if is_autonomous else "uWQ"

    target_width = 11
    qrane_padding = " " * (target_width - 5)
    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"
    check_api_keys(config, qrane_prefix)

    if args.tui and tui:
        try:
            with tui.QonqreteTUI() as ui:
                run_orchestration(args, prefix, is_autonomous, config, ui)
        except KillSignal:
            print(f"\n{Colors.RED}︻デ┳═ー{Colors.WHITE} - - - {Colors.RED}Qilled{Colors.WHITE} all agents in the Qage...{Colors.R}")
            print(); print(f"{Colors.WHITE}QonQrete session ended by {Colors.RED}guns{Colors.R}{Colors.WHITE}.{Colors.R}")
        except Exception:
            traceback.print_exc(); print("TUI Crashed.")
    else:
        try:
            run_orchestration(args, prefix, is_autonomous, config, ui=None)
        except KillSignal:
            print(f"\r{qrane_prefix}{Colors.RED}︻デ┳═ー - - - Qilled all agents in the Qage...{Colors.R}")
            print(); print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended by {Colors.RED}guns{Colors.R}{Colors.WHITE}.{Colors.R}")
        except KeyboardInterrupt:
            print(f"\r{qrane_prefix}{Colors.RED}︻デ┳═ー - - - Qilled all agents in the Qage...{Colors.R}")
            print(); print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended by {Colors.RED}guns{Colors.R}{Colors.WHITE}.{Colors.R}")
        except Exception as e:
            traceback.print_exc()

def run_orchestration(args, prefix, is_autonomous, config, ui):
    worqspace = get_worqspace()
    path_manager = PathManager(worqspace)
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("qrane")
    if create_manifest:
        create_manifest(worqspace)
        start_stage(worqspace, "INTAKE", os.environ.get("QONQ_RUN_KIND", "run"), 0, "Run intake metadata initialized.")
        complete_stage(worqspace, "INTAKE", os.environ.get("QONQ_RUN_KIND", "run"), 0, artifacts=["task/task-intake-bridge.v1.json"], notes=["Legacy qage intake linked into canonical run manifest bridge."], success=True)

    final_mode = args.mode if args.mode else config.get('options', {}).get('mode', 'program')
    final_sens = args.briq_sensitivity if args.briq_sensitivity is not None else config.get('options', {}).get('briq_sensitivity', 7)

    os.environ['QONQ_MODE'] = final_mode
    os.environ['QONQ_SENSITIVITY'] = str(final_sens)

    # Max cycles: CLI overrides config
    max_cycles = config.get('options', {}).get('auto_cycle_limit', 4)
    if args.cyqles is not None:
        max_cycles = max(1, min(50, args.cyqles))  # Clamp to 1-50
    target_width = 11
    qrane_padding = " " * (target_width - 5)
    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"

    # Get agent enable/disable settings
    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    use_qontextor = config.get('options', {}).get('use_qontextor', True)
    use_qontrabender = config.get('options', {}).get('use_qontrabender', True)

    if not ui:
        print(f"{qrane_prefix}Seeding worQspace in Qage at: {worqspace}\r")
        print(f"{qrane_prefix}Importing gateQeeper's tasq.md...\r")
        time.sleep(0.3)
        print(f"{qrane_prefix}Initiating Qrew... (Mode: {final_mode}, Sens: {final_sens}, Cyqles: {max_cycles})\r")
        
        # Show agent status
        qomp_status = f"{Colors.GREEN}ON{Colors.R}" if use_qompressor else f"{Colors.RED}OFF{Colors.R}"
        qont_status = f"{Colors.GREEN}ON{Colors.R}" if use_qontextor else f"{Colors.RED}OFF{Colors.R}"
        qonb_status = f"{Colors.GREEN}ON{Colors.R}" if use_qontrabender else f"{Colors.RED}OFF{Colors.R}"
        print(f"{qrane_prefix}Agents: Qompressor={qomp_status}, Qontextor={qont_status}, Qontrabender={qonb_status}\r")
        time.sleep(0.3)
    else:
        ui.log_main(f"{qrane_prefix}Initiating Qrew... (Mode: {final_mode})")

    AGENT_COLORS = {"qrystallizer": Colors.YELLOW, "tasqleveler": Colors.YELLOW, "instruqtor": Colors.LIME, "calqulator": Colors.GREEN, "construqtor": Colors.C, "inspeqtor": Colors.MAGENTA, "qontextor": Colors.YELLOW, "qompressor": Colors.B, "qontrabender": Colors.MAGENTA}

    # --- Initial Dual-Core Warmup (Sqrapyard Detection) ---
    # Checks if qodeyard was seeded. If so, generate Skeletons (Fast) and Context (Smart).
    if any(path_manager.qodeyard_dir.iterdir()):

        # Use a temporary env for initial runs
        initial_env = os.environ.copy()
        initial_env["CYCLE_NUM"] = "0"

        # 1. Run Qompressor (FAST - Structural Warmup) - if enabled
        if use_qompressor:
            msg = "Seeded qodeyard detected. Warming up Qompressor (Skeleton Cache)..."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{msg}\r")

            qompressor_cmd = ["python3", str(AGENT_MODULE_DIR / "qompressor.py"), str(path_manager.qodeyard_dir), str(path_manager.bloq_dir)]
            qonsole_log_path = path_manager.get_qonsole_log_path("qompressor_warmup")
            events_log_path = path_manager.get_events_log_path("qompressor_warmup")

            if not run_agent("qompressor", qompressor_cmd, prefix, AGENT_COLORS.get("qompressor"), logger, qonsole_log_path, events_log_path, initial_env, ui):
                 if ui: ui.log_main(f"{qrane_prefix}{Colors.RED}Qompressor warmup failed.{Colors.R}")
                 else: print(f"{qrane_prefix}{Colors.RED}Qompressor warmup failed.{Colors.R}\r")
                 if record_support_service:
                     record_support_service(worqspace, "qompressor_warmup", 0, artifacts=["bloq.d"] if path_manager.bloq_dir.exists() else [], notes=["Warmup skeleton generation failed."], success=False)
            elif record_support_service:
                record_support_service(worqspace, "qompressor_warmup", 0, artifacts=["bloq.d"] if path_manager.bloq_dir.exists() else [], notes=["Warmup skeleton generation completed."], success=True)
        else:
            msg = "Qompressor DISABLED - skipping skeleton generation."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

        # 2. Run Qontextor (SLOW/SMART - Semantic Warmup) - if enabled
        if use_qontextor:
            msg = "Running initial Qontextor scan (Semantic Indexing)..."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{msg}\r")

            qontextor_cmd = ["python3", str(AGENT_MODULE_DIR / "qontextor.py"), str(path_manager.qodeyard_dir), str(path_manager.qontext_dir)]
            qonsole_log_path = path_manager.get_qonsole_log_path("qontextor_initial")
            events_log_path = path_manager.get_events_log_path("qontextor_initial")

            if not run_agent("qontextor", qontextor_cmd, prefix, AGENT_COLORS.get("qontextor"), logger, qonsole_log_path, events_log_path, initial_env, ui):
                if ui: ui.log_main(f"{qrane_prefix}{Colors.RED}Initial Qontextor scan failed. Aborting.{Colors.R}")
                else: print(f"{qrane_prefix}{Colors.RED}Initial Qontextor scan failed. Aborting.{Colors.R}\r")
                if record_support_service:
                    record_support_service(worqspace, "qontextor_initial", 0, artifacts=["qontext.d"] if path_manager.qontext_dir.exists() else [], notes=["Initial context warmup failed."], success=False)
                if finalize_manifest:
                    finalize_manifest(worqspace, "failed", "Initial qontextor warmup failed.")
                return
            else:
                if ui: ui.log_main(f"{qrane_prefix}Dual-Core Memory Primed.")
                else: print(f"{qrane_prefix}Dual-Core Memory Primed.\r")
                if record_support_service:
                    record_support_service(worqspace, "qontextor_initial", 0, artifacts=["qontext.d"] if path_manager.qontext_dir.exists() else [], notes=["Initial context warmup completed."], success=True)
        else:
            msg = "Qontextor DISABLED - skipping context generation."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

        # 3. Run Qontrabender (Cache Management) - if enabled
        if use_qontrabender:
            msg = "Running Qontrabender (Hybrid Cache Assembly)..."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{msg}\r")

            qontrabender_cmd = ["python3", str(AGENT_MODULE_DIR / "qontrabender.py"), "--check"]
            qonsole_log_path = path_manager.get_qonsole_log_path("qontrabender_warmup")
            events_log_path = path_manager.get_events_log_path("qontrabender_warmup")

            if not run_agent("qontrabender", qontrabender_cmd, prefix, AGENT_COLORS.get("qontrabender"), logger, qonsole_log_path, events_log_path, initial_env, ui):
                if ui: ui.log_main(f"{qrane_prefix}{Colors.YELLOW}Qontrabender warmup had issues (non-critical).{Colors.R}")
                else: print(f"{qrane_prefix}{Colors.YELLOW}Qontrabender warmup had issues (non-critical).{Colors.R}\r")
                if record_support_service:
                    record_support_service(worqspace, "qontrabender_warmup", 0, artifacts=["qache.d/manifest.json"] if (worqspace / "qache.d" / "manifest.json").exists() else [], notes=["Warmup cache check had issues."], success=False)
            else:
                if ui: ui.log_main(f"{qrane_prefix}Qache Ready.")
                else: print(f"{qrane_prefix}Qache Ready.\r")
                if record_support_service:
                    record_support_service(worqspace, "qontrabender_warmup", 0, artifacts=["qache.d/manifest.json"] if (worqspace / "qache.d" / "manifest.json").exists() else [], notes=["Warmup cache check completed."], success=True)
        else:
            msg = "Qontrabender DISABLED - skipping cache management."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

    cycle = 1
    session_failed = False
    user_aborted = False
    user_quit = False
    bounded_stop = False
    partial_stop = False
    repair_blocked_by_cycle_limit = False
    no_midrun_questions = False
    legacy_continuation = legacy_cycle_continuation_enabled(config)
    repair_attempts_started = 0
    repair_cycles: set[int] = set()

    try:
        while True:
            if is_autonomous and max_cycles > 0 and cycle > max_cycles:
                limit_str = f"{Colors.C}{max_cycles}{Colors.R}"
                msg = f"Max cyQle limit hit ({limit_str}) - Edit config.yaml to change this."
                if ui: ui.log_main(f"{qrane_prefix}{msg}")
                else: print(f"{qrane_prefix}{msg}\r")
                if cycle in repair_cycles:
                    repair_blocked_by_cycle_limit = True
                    partial_stop = True
                break

            env = os.environ.copy()
            env["CYCLE_NUM"] = str(cycle)
            if cycle in repair_cycles:
                env["QONQ_REPAIR_MODE"] = "1"
                env["QONQ_REPAIR_PLAN_PATH"] = str(repair_plan_path(worqspace))
                env["QONQ_REPAIR_PASS_INDEX"] = str(repair_attempts_started)
            else:
                env.pop("QONQ_REPAIR_MODE", None)
                env.pop("QONQ_REPAIR_PLAN_PATH", None)
                env.pop("QONQ_REPAIR_PASS_INDEX", None)

            try:
                with open(path_manager.root / 'pipeline_config.yaml', 'r') as f:
                    pipeline_config = yaml.safe_load(f)
            except:
                if ui: ui.log_main("Config Error"); break
                else: print("Config Error"); break

            def resolve_template(tpl):
                if "{N}" in tpl: return tpl.replace("{N}", str(cycle))
                return tpl

            agents_to_run = []
            agent_configs = config.get('agents', {})
            is_repair_cycle = cycle in repair_cycles

            for agent_def in pipeline_config.get('agents', []):
                name = agent_def['name']
                agent_config = get_agent_config(agent_configs, name)
                provider = agent_config.get('provider', None)

                # Skip agents that only run on cycle 1 (e.g., TasqLeveler)
                if agent_def.get('cycle_1_only', False) and cycle > 1:
                    continue

                # Skip disabled agents
                if name == 'qompressor' and not use_qompressor:
                    continue
                if name == 'qontextor' and not use_qontextor:
                    continue
                if name == 'qontrabender' and not use_qontrabender:
                    continue
                if is_repair_cycle and name in {'instruqtor', 'calqulator'}:
                    continue
                
                # ═══════════════════════════════════════════════════════════════
                # v1.0.2: Skip qontrabender if NOT using Gemini for construqtor
                # Qontrabender is specifically for Gemini's context caching feature
                # ═══════════════════════════════════════════════════════════════
                construqtor_cfg = agent_configs.get('construqtor', {})
                construqtor_provider = construqtor_cfg.get('provider', 'gemini').lower()
                
                # Skip qontrabender unless construqtor is using Gemini
                if name == 'qontrabender' and construqtor_provider != 'gemini':
                    continue
                
                # Skip calqulator if using local construqtor (no API costs to calculate)
                if name == 'calqulator' and construqtor_provider == 'local':
                    continue

                # --- DYNAMIC LOCAL AGENT LOADER ---
                if provider == 'local':
                    model_name = agent_config.get('model')
                    if not model_name:
                        if ui: ui.log_main(f"Config Error: 'model' not specified for local agent '{name}'")
                        else: print(f"Config Error: 'model' not specified for local agent '{name}'")
                        session_failed = True; break
                    
                    script = f"{model_name}.py"
                    
                    # Security check: ensure the model name is a simple alphanumeric name
                    if not re.match(r'^[a-zA-Z0-9_]+$', model_name):
                        if ui: ui.log_main(f"Config Error: Invalid 'model' name for local agent '{name}'")
                        else: print(f"Config Error: Invalid 'model' name for local agent '{name}'")
                        session_failed = True; break
                else:
                    script = agent_def['script']
                # --- END DYNAMIC LOADER ---

                # Handle single or multiple inputs
                input_val = agent_def['input']
                if isinstance(input_val, list):
                    input_paths = [str(path_manager.root / resolve_template(p)) for p in input_val]
                else:
                    input_paths = [str(path_manager.root / resolve_template(input_val))]

                cmd = ["python3", str(AGENT_MODULE_DIR / script)] + input_paths

                # Handle single or multiple outputs
                output_val = agent_def['output']
                if isinstance(output_val, list):
                    output_paths = [str(path_manager.root / resolve_template(p)) for p in output_val]
                    cmd.extend(output_paths)
                else:
                    cmd.append(str(path_manager.root / resolve_template(output_val)))

                agents_to_run.append((name, cmd))

            if ui:
                ui.log_main(f"--- Starting Cycle {cycle} ---")
            else:
                start_msg = f"Starting {Colors.C}cyQle {cycle}{Colors.R}..."
                print(f"{qrane_prefix}{start_msg}\r")
                if args.auto:
                     inst_padding = " " * 1
                     print(f"{Colors.B}〘{prefix}〙『{Colors.LIME}instruQtor{Colors.B}』{inst_padding}⸎ {Colors.R}Ingesting cyqle{cycle}_tasq.md...\r")

            previous_log_path = None
            for name, cmd in agents_to_run:
                env["QONQ_PREVIOUS_LOG"] = str(previous_log_path) if previous_log_path else ""

                canonical_stage = STAGE_ALIAS_MAP.get(name)
                if canonical_stage and start_stage:
                    start_stage(worqspace, canonical_stage, name, cycle, f"Stage {canonical_stage} starting via legacy alias '{name}'.")
                    stage_msg = f"Stage {canonical_stage} [legacy: {name}]"
                    if ui:
                        ui.log_main(f"{qrane_prefix}{stage_msg}")
                    else:
                        print(f"{qrane_prefix}{stage_msg}\r")

                qonsole_log_path = path_manager.get_qonsole_log_path(name)
                events_log_path = path_manager.get_events_log_path(name)

                if not run_agent(name, cmd, prefix, AGENT_COLORS.get(name, Colors.WHITE), logger, qonsole_log_path, events_log_path, env, ui):
                    if canonical_stage and record_agent_completion:
                        record_agent_completion(worqspace, name, cycle, success=False)
                    elif record_support_service:
                        record_support_service(worqspace, name, cycle, artifacts=[], notes=[f"Support service '{name}' failed."], success=False)
                    session_failed = True; break

                previous_log_path = qonsole_log_path
                if record_agent_completion:
                    record_agent_completion(worqspace, name, cycle, success=True)
                if name in {'qrystallizer', 'tasqleveler'}:
                    ready, status = load_task_spec_status(worqspace)
                    if ready:
                        no_midrun_questions = True
                        env["QONQ_NO_MIDRUN_QUESTIONS"] = "1"
                        if legacy_continuation:
                            msg = (
                                f"Clarification accepted with Task Spec status {status}. "
                                "Mid-run questioning disabled. Legacy continuation remains enabled by explicit compatibility opt-in."
                            )
                        else:
                            msg = (
                                f"Clarification accepted with Task Spec status {status}. "
                                "Mid-run questioning disabled and legacy reqap continuation downgraded to compatibility-only."
                            )
                        if ui:
                            ui.log_main(f"{qrane_prefix}{msg}")
                        else:
                            print(f"{qrane_prefix}{msg}\r")

                # ═══════════════════════════════════════════════════════════════
                # GateQeeper — Cost Confirmation Gate
                # After CalQulator estimates costs, optionally prompt user
                # ═══════════════════════════════════════════════════════════════
                if name == 'calqulator' and config.get('options', {}).get('cost_confirmation_gate', False):
                    gate_prefix = f"{Colors.B}〘{prefix}〙『{Colors.YELLOW}GateQeeper{Colors.B}』      ⸎{Colors.R}"
                    if no_midrun_questions:
                        if ui:
                            ui.log_main("GateQeeper bypassed: no-mid-run-question enforcement active.")
                        else:
                            print(f"{gate_prefix} Gate bypassed: no-mid-run-question enforcement active.")
                        continue
                    if ui:
                        ui.log_main("GateQeeper: Cost estimate above. Confirm to proceed?")
                    else:
                        print(f"\n{gate_prefix} Cost estimate above. Proceed with this run? [y/N] ", end="", flush=True)
                        try:
                            answer = input().strip().lower()
                        except EOFError:
                            answer = "n"
                        if answer not in ('y', 'yes'):
                            print(f"{gate_prefix} Run cancelled by GateQeeper.")
                            session_failed = True
                            break
                        print(f"{gate_prefix} Confirmed. Proceeding...")

            if session_failed: break

            res = handle_cheqpoint(
                cycle,
                is_autonomous,
                path_manager.get_reqap_path(cycle),
                prefix,
                path_manager,
                ui,
                no_midrun_questions=no_midrun_questions,
                legacy_continuation=legacy_continuation,
                config=config,
                repair_attempts_started=repair_attempts_started,
            )
            if res == 'QUIT':
                user_quit = True
                break
            if res == 'STOP':
                bounded_stop = True
                break
            if res == 'STOP_PARTIAL':
                partial_stop = True
                break
            if res == 'REPAIR':
                repair_attempts_started += 1
                repair_cycles.add(cycle + 1)
            cycle += 1

    except KeyboardInterrupt:
        if not ui:
            raise
        session_failed = True
        user_aborted = True

    if not ui:
        print()
        if user_aborted:
             print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended by {Colors.YELLOW}user{Colors.R}{Colors.WHITE}.{Colors.R}\r")
        elif session_failed:
             print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended with {Colors.RED}errors{Colors.R}{Colors.WHITE}.{Colors.R}\r")
        else:
             print(f"{qrane_prefix}QonQrete session finished. Enjoy :)\r")
    if finalize_manifest:
        if user_aborted:
            finalize_manifest(worqspace, "aborted", "Run aborted by user.")
        elif session_failed:
            finalize_manifest(worqspace, "failed", "Run ended with errors.")
        elif user_quit:
            finalize_manifest(worqspace, "partial", "Run ended at legacy user-gated cheqpoint.")
        elif partial_stop:
            detail = "Run ended with explicit continuable repair state."
            if repair_blocked_by_cycle_limit:
                detail = "Run stopped before executing scheduled repair because the configured cycle limit was reached."
            finalize_manifest(worqspace, "partial", detail)
        elif bounded_stop:
            finalize_manifest(worqspace, "completed", "Run ended after bounded clarified bridge pass without implicit legacy continuation.")
        else:
            finalize_manifest(worqspace, "completed", "Run finished without runtime errors.")

if __name__ == "__main__":
    main()
