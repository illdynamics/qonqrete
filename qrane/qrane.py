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
    agent_display_name = agent_name.replace('q', 'Q')
    target_width = 11
    padding = " " * (target_width - len(agent_display_name))
    qrane_padding = " " * (target_width - 5)

    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"
    agent_prefix = f"{Colors.B}〘{prefix}〙『{color}{agent_display_name}{Colors.B}』{padding}⸎ {Colors.R}"

    VISIBLE_KEYWORDS = [
        "Handing off", "Processing", "Executed", "Wrote", "reQap",
        "Checking", "Generating", "Ingesting", "Architect", "Plan",
        "Found", "Summary"
    ]

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
                            if any(x in clean for x in VISIBLE_KEYWORDS):
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
                        if r == proc.stdout and any(x in clean for x in VISIBLE_KEYWORDS):
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
            traceback.print_exc() # Print traceback for debugging
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
            # [FIX] Use regex to find the Assessment line regardless of leading chars/lists
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
        'deepseek': 'DEEPSEEK_API_KEY'
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
    final_sens = args.briq_sensitivity if args.briq_sensitivity is not None else config.get('options', {}).get('briq_sensitivity', 5)

    os.environ['QONQ_MODE'] = final_mode
    os.environ['QONQ_SENSITIVITY'] = str(final_sens)

    max_cycles = config.get('options', {}).get('auto_cycle_limit', 0)
    target_width = 11
    qrane_padding = " " * (target_width - 5)
    qrane_prefix = f"{Colors.B}〘{prefix}〙『{Colors.WHITE}Qrane{Colors.B}』{qrane_padding}⸎ {Colors.R}"

    if not ui:
        print(f"{qrane_prefix}Seeding worQspace in Qage at: {worqspace}\r")
        print(f"{qrane_prefix}Importing gateQeeper's tasq.md...\r")
        time.sleep(0.3)
        print(f"{qrane_prefix}Initiating Qrew... (Mode: {final_mode}, Sens: {final_sens})\r")
        time.sleep(0.3)
    else:
        ui.log_main(f"{qrane_prefix}Initiating Qrew... (Mode: {final_mode})")

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
            for agent_def in pipeline_config.get('agents', []):
                name = agent_def['name']
                script = agent_def['script']
                input_path = path_manager.root / resolve_template(agent_def['input'])
                output_path = path_manager.root / resolve_template(agent_def['output'])
                cmd = ["python3", str(AGENT_MODULE_DIR / script), str(input_path), str(output_path)]
                agents_to_run.append((name, cmd))

            AGENT_COLORS = {"instruqtor": Colors.LIME, "construqtor": Colors.C, "inspeqtor": Colors.MAGENTA}

            if ui:
                ui.log_main(f"--- Starting Cycle {cycle} ---")
            else:
                start_msg = f"Starting {Colors.C}cyQle {cycle}{Colors.R}..."
                print(f"{qrane_prefix}{start_msg}\r")
                if args.auto:
                     inst_padding = " " * 1
                     print(f"{Colors.B}〘{prefix}〙『{Colors.LIME}instruQtor{Colors.B}』{inst_padding}⸎ {Colors.R}Ingesting cyqle{cycle}_tasq.md...\r")

            for name, cmd in agents_to_run:
                qonsole_log_path = path_manager.get_qonsole_log_path(name)
                events_log_path = path_manager.get_events_log_path(name)
                if not run_agent(name, cmd, prefix, AGENT_COLORS.get(name, Colors.WHITE), logger, qonsole_log_path, events_log_path, env, ui):
                    session_failed = True; break

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
