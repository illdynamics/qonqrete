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

# Add script's directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from loader import Spinner, Colors
    from paths import PathManager
except ImportError:
    Spinner = None; Colors = None; PathManager = None

try:
    import tui
except ImportError:
    tui = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODULE_DIR = PROJECT_ROOT / "worqer"

class KillSignal(Exception): pass

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

    event_start_msg = f"Initiating {agent_display_name}..."
    with open(events_log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {event_start_msg}\n")

    if ui:
        ui.log_main(f"{qrane_prefix}{event_start_msg}")
        try:
            with subprocess.Popen(command, cwd=str(get_worqspace()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=env, universal_newlines=True) as proc, \
                 open(qonsole_log_path, 'a', encoding='utf-8') as qonsole_log:

                reads = [proc.stdout, proc.stderr]
                while True:
                    check_tui_keys(ui, proc)
                    readable, _, _ = select.select(reads, [], [], 0.05)
                    for r in readable:
                        line = r.readline()
                        if not line: reads.remove(r); continue

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
                while True:
                    readable, _, _ = select.select(reads, [], [], 0.05)
                    if not readable and proc.poll() is not None: break
                    for r in readable:
                        line = r.readline()
                        if not line:
                            reads.remove(r)
                            continue

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

def handle_cheqpoint(cycle: int, is_autonomous: bool, reqap_path: Path, prefix: str, path_manager: PathManager, ui=None) -> str:
    target_width = 11
    gatekeeper_name = "gateQeeper"
    p_padding = " " * (target_width - len(gatekeeper_name))
    gate_prefix = f"{Colors.B}〘{prefix}〙『{Colors.YELLOW}{gatekeeper_name}{Colors.B}』{p_padding}⸎ {Colors.R}"

    assessment = "Unknown"
    content = ""
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

    if is_autonomous:
        msg = "Autonomous Mode: Qontinuing..."
        if ui: ui.log_main(f"{gate_prefix}{msg}")
        else:
            print("\n" + f"{Colors.YELLOW}=== Cheqpoint {cycle:03d} ==={Colors.R}")
            print(content)
            print(f"{gate_prefix}{msg}")
        promote_reqap(cycle, prefix, path_manager, ui=ui)
        return 'QONTINUE'

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
        'qwen': 'QWEN_API_KEY'
    }

    missing_keys = []
    for provider in providers:
        if provider == 'gemini':
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

    AGENT_COLORS = {"tasqleveler": Colors.YELLOW, "instruqtor": Colors.LIME, "calqulator": Colors.GREEN, "construqtor": Colors.C, "inspeqtor": Colors.MAGENTA, "qontextor": Colors.YELLOW, "qompressor": Colors.B, "qontrabender": Colors.MAGENTA}

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
                return
            else:
                if ui: ui.log_main(f"{qrane_prefix}Dual-Core Memory Primed.")
                else: print(f"{qrane_prefix}Dual-Core Memory Primed.\r")
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
            else:
                if ui: ui.log_main(f"{qrane_prefix}Qache Ready.")
                else: print(f"{qrane_prefix}Qache Ready.\r")
        else:
            msg = "Qontrabender DISABLED - skipping cache management."
            if ui: ui.log_main(f"{qrane_prefix}{msg}")
            else: print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

    cycle = 1
    session_failed = False
    user_aborted = False

    try:
        while True:
            if is_autonomous and max_cycles > 0 and cycle > max_cycles:
                limit_str = f"{Colors.C}{max_cycles}{Colors.R}"
                msg = f"Max cyQle limit hit ({limit_str}) - Edit config.yaml to change this."
                if ui: ui.log_main(f"{qrane_prefix}{msg}")
                else: print(f"{qrane_prefix}{msg}\r")
                break

            env = os.environ.copy()
            env["CYCLE_NUM"] = str(cycle)

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

            for agent_def in pipeline_config.get('agents', []):
                name = agent_def['name']
                agent_config = agent_configs.get(name, {})
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

                qonsole_log_path = path_manager.get_qonsole_log_path(name)
                events_log_path = path_manager.get_events_log_path(name)

                if not run_agent(name, cmd, prefix, AGENT_COLORS.get(name, Colors.WHITE), logger, qonsole_log_path, events_log_path, env, ui):
                    session_failed = True; break

                previous_log_path = qonsole_log_path

            if session_failed: break

            res = handle_cheqpoint(cycle, is_autonomous, path_manager.get_reqap_path(cycle), prefix, path_manager, ui)
            if res == 'QUIT': break
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

if __name__ == "__main__":
    main()
