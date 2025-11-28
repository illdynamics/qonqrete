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
import shutil

# Add script's directory to the Python path FIRST to ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from lib import Spinner, Colors
except ImportError:
    Spinner = None; Colors = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODULE_DIR = PROJECT_ROOT / "worqer"

def getch():
    try:
        import tty, termios
        fd = sys.stdin.fileno(); old_settings = termios.tcgetattr(fd)
        try: tty.setraw(sys.stdin.fileno()); ch = sys.stdin.read(1)
        finally: termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
    except (ImportError, ModuleNotFoundError):
        import msvcrt
        return msvcrt.getch().decode()

def format_line(line: str, agent_name: str, filters: dict, manipulators: dict) -> str | None:
    agent_filters = filters.get(agent_name, [])
    for f in agent_filters:
        if f in line: return None
    line = line.replace("successful", f"{Colors.GREEN}successful{Colors.R}")
    line = line.replace("failed", f"{Colors.RED}failed{Colors.R}")
    line = re.sub(r"(STDERR)", f"{Colors.RED}\1{Colors.R}", line, flags=re.IGNORECASE)
    return line

def get_worqspace() -> Path:
    env_path = os.environ.get("QONQ_WORKSPACE")
    return Path(env_path) if env_path else PROJECT_ROOT / "worqspace"

def run_agent(agent_name: str, command: list[str], prefix: str, color: str, logger: logging.Logger, log_file: Path, env: dict) -> bool:

    # 1. Setup Visuals
    agent_display_name = agent_name.replace('q', 'Q')
    # Alignment Logic: Max 11 chars.
    # construQtor (11) = 0 spaces
    # instruQtor (10) = 1 space
    # inspeQtor (9) = 2 spaces
    padding = " " * (11 - len(agent_display_name))
    spinner_prefix = f"〘{prefix}〙"

    spinner = Spinner(prefix=spinner_prefix, message=f"Running {agent_display_name}...")
    logger.info(f"Exec: {' '.join(command)}")

    # 2. Start Spinner
    spinner.start()

    try:
        # 3. Execute with CAPTURE_OUTPUT=True
        proc = subprocess.run(
            command,
            cwd=str(get_worqspace()),
            capture_output=True,
            text=True,
            env=env
        )

        # 4. Stop Spinner
        spinner.stop()

        # 5. Write to specific log file
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"--- EXECUTION START: {agent_name} ---\n")
            if proc.stdout: f.write(proc.stdout + "\n")
            if proc.stderr: f.write(proc.stderr + "\n")
            f.write(f"--- EXECUTION END: {agent_name} (Return Code: {proc.returncode}) ---\n\n")

        # 6. Handle Errors
        if proc.returncode != 0:
            error_prefix = f"{Colors.RED}〘{prefix}〙『{agent_display_name}』{padding} ⸎ {Colors.R}"
            print(f"{error_prefix} {Colors.RED}ERROR: Agent exited with non-zero status code: {proc.returncode}{Colors.R}")
            if proc.stderr:
                for line in proc.stderr.strip().split('\n'):
                    print(f"{error_prefix} {Colors.RED}{line}{Colors.R}")
            return False

        # 7. Print Success Output (Formatted)
        if proc.stdout:
            output_prefix = f"{color}〘{prefix}〙『{agent_display_name}』{padding} ⸎ {Colors.R}"
            for line in proc.stdout.strip().split('\n'):
                # [SHERLONQ LOG FILTER] Whitelist for visible logs
                clean_line = line.strip()
                if "Handing off to Gemini" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "Processing Briq" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "Executed Briq" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "Wrote Briq" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "reQap written" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "Checking" in line:
                    print(f"{output_prefix} {clean_line}")
                elif "CRITICAL" in line or "ERROR" in line:
                    print(f"{output_prefix} {Colors.RED}{clean_line}{Colors.R}")

    except Exception as e:
        spinner.stop()
        print(f"{Colors.RED}A critical error occurred while running {agent_name}: {e}{Colors.R}")
        return False

    return True

def promote_reqap_to_tasq(reqap_path: Path, next_tasq_path: Path, cycle: int, logger: logging.Logger, prefix: str):
    try:
        # [SHERLONQ IDENTITY] Qrane Action
        agent_display_name = "Qrane"
        padding = " " * (11 - len(agent_display_name)) # 6 spaces
        output_prefix = f"{Colors.B}〘{prefix}〙『{agent_display_name}』{padding} ⸎ {Colors.R}"

        print(f"{output_prefix} Promoting reQap to new tasQ for cyqle {cycle+1}...")

        with open(reqap_path, 'r', encoding='utf-8') as f:
            content = f.read()

        new_tasq_content = f"# Cycle {cycle+1} Instructions\n\n**Context from Cycle {cycle} reQap:**\n\n---\n\n{content}"

        os.makedirs(next_tasq_path.parent, exist_ok=True)
        with open(next_tasq_path, 'w', encoding='utf-8') as f:
            f.write(new_tasq_content)

        print(f"{output_prefix} Successfully created {next_tasq_path.name}.")
        return True
    except Exception:
        return False

def handle_cheqpoint(cycle: int, args, logger, reqap_path: Path, prefix: str) -> str:
    worqspace = get_worqspace()
    next_tasq_path = worqspace / "tasq.d" / f"cyqle{cycle+1}_tasq.md"

    # [SHERLONQ IDENTITY] Qrane Action
    qrane_padding = " " * 6
    qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding} ⸎ {Colors.R}"
    print(f"{qrane_prefix} Handling cheQpoint")

    content = "[ERROR] Could not read reQap"
    assessment = "Unknown"

    try:
        with open(reqap_path, 'r', encoding='utf-8') as f:
            content = f.read()
            first_line = content.split('\n', 1)[0]
            if "Assessment:" in first_line:
                assessment = first_line.split(":", 1)[1].strip()
    except Exception:
        pass

    # Print Cheqpoint UI
    header_text = f" cheQpoint {cycle:03d} "
    header_len = 78
    padding = (header_len - len(header_text)) // 2
    header = f"{Colors.YELLOW}{Colors.BOLD}{'='*padding}{Colors.WHITE}{Colors.BOLD}{header_text}{Colors.YELLOW}{Colors.BOLD}{'='*padding}{Colors.R}"

    print("\n" + header)
    print(content)
    print(Colors.YELLOW + Colors.BOLD + "="*header_len + "\n" + Colors.R)

    if args.auto:
        # [SHERLONQ LOG] Autonomous Message
        print(f"{qrane_prefix} Autonomous mode... No gateQeeper approval required, we will Qontinue..")
        promote_reqap_to_tasq(reqap_path, next_tasq_path, cycle, logger, prefix)
        return 'QONTINUE'

    # Interactive Logic
    gatekeeper_name = "gateQeeper"
    padding = " " * (11 - len(gatekeeper_name))
    prompt_prefix = f"{Colors.YELLOW}〘{prefix}〙『{gatekeeper_name}』{padding} ⸎  {Colors.R}"

    assessment_color = Colors.YELLOW
    if "Success" in assessment: assessment_color = Colors.GREEN
    elif "Failure" in assessment: assessment_color = Colors.RED

    print(f"{prompt_prefix}{Colors.WHITE}Result: {assessment_color}{assessment}{Colors.R}")
    print(f"{prompt_prefix}[Q]ontinue, [T]weaQ (Edit), [X]Quit")

    while True:
        sys.stdout.write(f"{prompt_prefix}{Colors.WHITE}Selection: {Colors.R}")
        sys.stdout.flush()
        choice = getch().lower()
        print(choice)

        if choice == 'q':
            # [SHERLONQ LOG] Manual Continue Message
            print(f"{qrane_prefix} gateQeeper's reQap imported...")
            promote_reqap_to_tasq(reqap_path, next_tasq_path, cycle, logger, prefix)
            return 'QONTINUE'
        elif choice == 'x':
            return 'QUIT'
        elif choice == 't':
            editor = os.environ.get('EDITOR', 'vim')
            subprocess.run([editor, str(reqap_path)])
            continue
        elif ord(choice) == 3: # Ctrl+C
            return 'QUIT'

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--tui", action="store_true")
    parser.add_argument("-w", "--wonqrete", action="store_true")
    args = parser.parse_args(argv)

    if Spinner is None or Colors is None:
        print("Error: lib.py not found.")
        sys.exit(1)

    worqspace = get_worqspace()
    log_dir = worqspace / "struqture"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(filename=log_dir / "main_qrane.log", level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger("qrane")

    prefix = "aWQ" if args.auto and args.wonqrete else "aQQ" if args.auto else "QQ"
    AGENT_COLORS = {"instruqtor": Colors.B, "construqtor": Colors.C, "inspeqtor": Colors.MAGENTA}

    # Qrane Identity
    qrane_padding = " " * 6
    qrane_prefix = f"{Colors.B}〘{prefix}〙『Qrane』{qrane_padding} ⸎ {Colors.R}"

    try:
        try:
            with open(worqspace / 'config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
        except: config = {}
        max_cycles = config.get('options', {}).get('auto_cycle_limit', 0)

        # [SHERLONQ LOG] Specific Startup Message
        print(f"{qrane_prefix} Importing gateQeeper's tasq.md...")
        time.sleep(0.3)
        print(f"{qrane_prefix} Initiating worQers...")
        time.sleep(0.3)

        cycle = 1
        while True:
            if args.auto and max_cycles != 0 and cycle > max_cycles: break

            env = os.environ.copy()
            env["CYCLE_NUM"] = str(cycle)
            env["TASQ_NUM"] = "1"

            tasq_input = worqspace / "tasq.d" / f"cyqle{cycle}_tasq.md"
            if not tasq_input.exists():
                print(f"No task found for cycle {cycle}. Exiting.")
                break

            # [SHERLONQ FIX] Alignment Fix: instruQtor (10 chars) needs 1 space to match 11.
            # Previously hardcoded to 3 spaces. Now fixed.
            instruqtor_padding = " " * 1
            ingesting_prefix = f"{Colors.B}〘{prefix}〙『instruQtor』{instruqtor_padding} ⸎ {Colors.R}"
            print(f"{ingesting_prefix} Ingesting {tasq_input.name}...")

            # Define Log Files
            logs = {
                "instruqtor": log_dir / f"cyqle{cycle}_instruqtor.log",
                "construqtor": log_dir / f"cyqle{cycle}_construqtor.log",
                "inspeqtor": log_dir / f"cyqle{cycle}_inspeqtor.log"
            }

            # Define Commands
            cmd_inst = [sys.executable, str(AGENT_MODULE_DIR / "instruqtor.py"), str(worqspace / "tasq.d"), str(worqspace / "briq.d")]
            cmd_cons = [sys.executable, str(AGENT_MODULE_DIR / "construqtor.py"), str(worqspace / "briq.d"), str(worqspace / "exeq.d" / f"cyqle{cycle}_summary.md")]
            cmd_insp = [sys.executable, str(AGENT_MODULE_DIR / "inspeqtor.py"), str(worqspace / "exeq.d" / f"cyqle{cycle}_summary.md"), str(worqspace / "reqap.d" / f"cyqle{cycle}_reqap.md")]

            # Run Cycle
            if not run_agent("instruqtor", cmd_inst, prefix, AGENT_COLORS["instruqtor"], logger, logs["instruqtor"], env): break
            if not run_agent("construqtor", cmd_cons, prefix, AGENT_COLORS["construqtor"], logger, logs["construqtor"], env): break
            if not run_agent("inspeqtor", cmd_insp, prefix, AGENT_COLORS["inspeqtor"], logger, logs["inspeqtor"], env): break

            if handle_cheqpoint(cycle, args, logger, worqspace / "reqap.d" / f"cyqle{cycle}_reqap.md", prefix) == 'QUIT': break
            cycle += 1

    except KeyboardInterrupt:
        print(f"\n{Colors.RED}User Interrupt (BreaQ){Colors.R}")
    finally:
        try:
            print(f"\n{qrane_prefix} QonQrete session finished.")
        except NameError:
             print(f"\n{Colors.BOLD}QonQrete session finished.{Colors.R}")

if __name__ == "__main__":
    main()
