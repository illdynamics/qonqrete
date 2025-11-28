#!/usr/bin/env python3
# qrane/qrane.py - QonQrete Qrane orchestrator
import argparse
import logging
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
import yaml
import re

# Add script's directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from loader import Spinner, Colors
except ImportError:
    Spinner = None; Colors = None

try:
    import tui
except ImportError:
    tui = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODULE_DIR = PROJECT_ROOT / "worqer"

def get_worqspace() -> Path:
    env_path = os.environ.get("QONQ_WORKSPACE")
    return Path(env_path) if env_path else PROJECT_ROOT / "worqspace"

def run_agent(agent_name: str, command: list[str], prefix: str, color: str, logger: logging.Logger, log_file: Path, env: dict, ui=None) -> bool:
    agent_display_name = agent_name.replace('q', 'Q')

    # --- TUI MODE (Split Screen) ---
    if ui:
        ui.log_main(f"[{agent_display_name}] Executing task...")
        try:
            with subprocess.Popen(
                command,
                cwd=str(get_worqspace()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                universal_newlines=True
            ) as proc:
                for line in proc.stdout:
                    ui.log_agent(f"[{agent_display_name}] {line.strip()}")
                    with open(log_file, 'a', encoding='utf-8') as f: f.write(line)

                stdout, stderr = proc.communicate()
                if stderr:
                    ui.log_agent(f"[{agent_display_name} STDERR] {stderr.strip()}")
                    with open(log_file, 'a', encoding='utf-8') as f: f.write(stderr)

                if proc.returncode != 0:
                    ui.log_main(f"[{agent_display_name}] FAILED (Code {proc.returncode})")
                    return False
                ui.log_main(f"[{agent_display_name}] Completed Successfully.")
                return True
        except Exception as e:
            ui.log_main(f"CRITICAL EXCEPTION: {e}")
            return False

    # --- HEADLESS MODE (Streaming + Spinner) ---
    else:
        # Target width 11 (based on 'construQtor')
        target_width = 11
        padding = " " * (target_width - len(agent_display_name))

        # Announce initiation using Qrane style
        qrane_padding = " " * (target_width - 5)
        # Tight alignment: No space before ⸎
        qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R}"
        print(f"{qrane_prefix} Initiating {agent_display_name}...")

        output_prefix = f"{Colors.B}〘{prefix}〙『{color}{agent_display_name}{Colors.B}』{padding}⸎ {Colors.R}"
        spinner = Spinner(prefix=f"〘{prefix}〙", message=f"Running {agent_display_name}...")

        spinner.start()

        try:
            # Use Popen to stream output line-by-line
            proc = subprocess.Popen(
                command,
                cwd=str(get_worqspace()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True
            )

            # Read stdout line by line
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break

                if line:
                    clean_line = line.strip()
                    if any(x in line for x in ["Handing off", "Processing", "Executed", "Wrote", "reQap", "Checking", "Generating", "Ingesting"]):
                        spinner.stop() # Clear spinner line
                        print(f"{output_prefix} {clean_line}")
                        spinner.start() # Resume spinner on new line

                    # Always log to file
                    with open(log_file, 'a', encoding='utf-8') as f: f.write(line)

            # Capture remaining stderr if any
            stderr = proc.stderr.read()
            if stderr:
                with open(log_file, 'a', encoding='utf-8') as f: f.write(stderr)

            spinner.stop()

            # Handle Failures
            if proc.returncode != 0:
                error_prefix = f"{Colors.RED}〘{prefix}〙『{agent_display_name}』{padding}⸎ {Colors.R}"
                print(f"{error_prefix} {Colors.RED}ERROR: Agent exited with code: {proc.returncode}{Colors.R}")

                if stderr:
                    print(f"{error_prefix} {Colors.RED}--- STDERR DUMP ---{Colors.R}")
                    for line in stderr.strip().split('\n'):
                        print(f"{error_prefix} {Colors.RED}{line}{Colors.R}")
                return False

            return True

        except KeyboardInterrupt:
            spinner.stop()
            try: proc.kill()
            except: pass
            print(f"\n{Colors.RED}User Interrupt (BreaQ) inside Agent.{Colors.R}")
            raise

        except Exception as e:
            spinner.stop()
            print(f"{Colors.RED}Critical Error: {e}{Colors.R}")
            return False

def handle_cheqpoint(cycle: int, args, reqap_path: Path, prefix: str, ui=None) -> str:
    # Read Assessment
    assessment = "Unknown"
    try:
        with open(reqap_path, 'r', encoding='utf-8') as f:
            if "Assessment:" in f.read().split('\n', 1)[0]:
                assessment = "Available"
    except: pass

    # --- TUI MODE ---
    if ui:
        ui.log_main(f"=== Cheqpoint {cycle} ===")
        if args.auto:
            ui.log_main("Autonomous Mode: Qontinuing...")
            promote_reqap(cycle, prefix, ui=ui)
            return 'QONTINUE'

        choice = ui.get_input("[Q]ontinue or [X]Quit")
        if choice.lower() == 'q':
            promote_reqap(cycle, prefix, ui=ui)
            return 'QONTINUE'
        return 'QUIT'

    # --- HEADLESS MODE ---
    else:
        # Checkpoint Header
        target_width = 11
        qrane_padding = " " * (target_width - 5)
        qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R}"

        header_text = f" cheQpoint {cycle:03d} "
        header_len = 78
        padding = (header_len - len(header_text)) // 2
        header = f"{Colors.YELLOW}{Colors.BOLD}{'='*padding}{Colors.WHITE}{Colors.BOLD}{header_text}{Colors.YELLOW}{Colors.BOLD}{'='*padding}{Colors.R}"

        print("\n" + header)

        try:
            with open(reqap_path, 'r', encoding='utf-8') as f:
                print(f.read())
        except: print("[Error reading reQap]")

        print(Colors.YELLOW + Colors.BOLD + "="*header_len + "\n" + Colors.R)

        if args.auto:
            print(f"{qrane_prefix} Autonomous mode... No gateQeeper approval required, we will Qontinue..")
            promote_reqap(cycle, prefix, ui=None)
            return 'QONTINUE'

        gatekeeper_name = "gateQeeper"
        p_padding = " " * (target_width - len(gatekeeper_name))
        prompt_prefix = f"{Colors.YELLOW}〘{prefix}〙『{gatekeeper_name}』{p_padding}⸎  {Colors.R}"

        print(f"{prompt_prefix}{Colors.WHITE}Result: {assessment}{Colors.R}")
        print(f"{prompt_prefix}[Q]ontinue, [T]weaQ (Edit), [X]Quit")

        while True:
            sys.stdout.write(f"{prompt_prefix}{Colors.WHITE}Selection: {Colors.R}")
            sys.stdout.flush()
            choice = getch().lower()
            if choice == 'q':
                print(f"{qrane_prefix} gateQeeper's reQap imported...")
                promote_reqap(cycle, prefix, ui=None)
                return 'QONTINUE'
            elif choice == 'x': return 'QUIT'
            elif choice == 't':
                editor = os.environ.get('EDITOR', 'vim')
                subprocess.run([editor, str(reqap_path)])
                continue
            elif ord(choice) == 3: return 'QUIT'

def promote_reqap(cycle: int, prefix: str, ui=None):
    ws = get_worqspace()
    src = ws / "reqap.d" / f"cyqle{cycle}_reqap.md"
    dst = ws / "tasq.d" / f"cyqle{cycle+1}_tasq.md"

    if src.exists():
        os.makedirs(dst.parent, exist_ok=True)
        with open(src, 'r') as f: content = f.read()
        with open(dst, 'w') as f: f.write(f"# Cycle {cycle+1}\n\n{content}")

        msg = f"Successfully created {dst.name}."
        start_msg = f"Starting cyQle {cycle+1}..."

        if ui:
            ui.log_main(msg)
            ui.log_main(start_msg)
        else:
            target_width = 11
            qrane_padding = " " * (target_width - 5)
            # Existing message
            print(f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R} {msg}")
            # [ADDED] The start cycle message
            print(f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R} {start_msg}")

def main():
    parser = argparse.ArgumentParser(prog="QonQrete")
    parser.add_argument("-a", "--auto", action="store_true", help="Autonomous Mode")
    parser.add_argument("-t", "--tui", action="store_true", help="Enable TUI")
    parser.add_argument("-w", "--wonqrete", action="store_true", help="Exp Mode")
    parser.add_argument("-V", "--version", action="version", version="QonQrete v0.1.0")
    args = parser.parse_args()

    prefix = "aQQ" if args.auto else "QQ"
    if args.wonqrete and args.auto: prefix = "aWQ"

    if args.tui and tui:
        try:
            with tui.QonqreteTUI() as ui:
                run_orchestration(args, prefix, ui)
        except Exception:
            traceback.print_exc()
            print("TUI Crashed.")
    else:
        run_orchestration(args, prefix, ui=None)

def run_orchestration(args, prefix, ui):
    worqspace = get_worqspace()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("qrane")

    try:
        with open(worqspace / 'config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
    except: config = {}
    max_cycles = config.get('options', {}).get('auto_cycle_limit', 0)

    target_width = 11
    qrane_padding = " " * (target_width - 5)

    if not ui:
        print(f"[INFO] Seeding worqspace in sandbox at: {worqspace}")

        qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R}"
        print(f"{qrane_prefix} Importing gateQeeper's tasq.md...")
        time.sleep(0.3)
        print(f"{qrane_prefix} Initiating Qrew...")
        time.sleep(0.3)

    cycle = 1
    session_failed = False
    user_aborted = False

    try:
        while True:
            if args.auto and max_cycles > 0 and cycle > max_cycles:
                msg = f"Max cyQle limit hit ({max_cycles}) - Edit config.yaml to change this."
                if ui: ui.log_main(msg)
                else: print(f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R} {msg}")
                break

            env = os.environ.copy()
            env["CYCLE_NUM"] = str(cycle)

            agents = [
                ("instruqtor", ["python3", str(AGENT_MODULE_DIR / "instruqtor.py"), str(worqspace/"tasq.d"), str(worqspace/"briq.d")]),
                ("construqtor", ["python3", str(AGENT_MODULE_DIR / "construqtor.py"), str(worqspace/"briq.d"), str(worqspace/"exeq.d"/f"cyqle{cycle}_summary.md")]),
                ("inspeqtor", ["python3", str(AGENT_MODULE_DIR / "inspeqtor.py"), str(worqspace/"exeq.d"/f"cyqle{cycle}_summary.md"), str(worqspace/"reqap.d"/f"cyqle{cycle}_reqap.md")])
            ]

            AGENT_COLORS = {"instruqtor": Colors.B, "construqtor": Colors.C, "inspeqtor": Colors.MAGENTA}

            if ui: ui.log_main(f"--- Starting Cycle {cycle} ---")
            else:
                if args.auto:
                     # 'instruQtor' is 10 chars. Target 11. Padding = 1 space.
                     # Format: 『instruQtor』 ⸎
                     inst_padding = " " * 1
                     print(f"{Colors.B}〘{prefix}〙『{Colors.B}instruQtor{Colors.B}』{inst_padding}⸎ {Colors.R} Ingesting cyqle{cycle}_tasq.md...")

            for name, cmd in agents:
                log_file = worqspace / "struqture" / f"cyqle{cycle}_{name}.log"
                if not run_agent(name, cmd, prefix, AGENT_COLORS[name], logger, log_file, env, ui):
                    session_failed = True
                    break

            if session_failed: break

            res = handle_cheqpoint(cycle, args, worqspace/"reqap.d"/f"cyqle{cycle}_reqap.md", prefix, ui)
            if res == 'QUIT': break

            cycle += 1

    except KeyboardInterrupt:
        if ui: pass
        else: print(f"\n{Colors.RED}User Interrupt (BreaQ){Colors.R}")
        session_failed = True
        user_aborted = True

    if not ui:
        qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding}⸎ {Colors.R}"

        if user_aborted:
             print(f"\n{qrane_prefix} {Colors.WHITE}QonQrete session ended by {Colors.YELLOW}user{Colors.R}{Colors.WHITE}.{Colors.R}")
        elif session_failed:
             print(f"\n{qrane_prefix} {Colors.WHITE}QonQrete session ended with {Colors.RED}errors{Colors.R}{Colors.WHITE}.{Colors.R}")
        else:
             print(f"\n{qrane_prefix} QonQrete session finished. Enjoy :)")

if __name__ == "__main__":
    main()
