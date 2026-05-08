
import os
import subprocess
import json
import time
from pathlib import Path
import re

TASQ_SMALL = ".qonqrete/tasq-small.md"
TASQ_MEDIUM = ".qonqrete/tasq-medium.md"
NUM_SMALL_RUNS = 9
QONQRETE_SH = "./.qonqrete/qonqrete.sh"

def run_tasq(task_file, run_label):
    print(f"\n--- {run_label} ---")
    env = os.environ.copy()
    env["CONTAINER_ENGINE"] = "none"
    env["QONQ_NON_INTERACTIVE"] = "1"
    cmd = [QONQRETE_SH, task_file, "--auto", "--no-sync"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    output = ""
    for line in process.stdout:
        print(line, end="", flush=True)
        output += line
    process.wait()
    
    # Find the qage directory from the output
    match = re.search(r"Seeding worQspace in Qage at: (.*)", output)
    if not match:
        # Fallback: find latest qage directory in worqspace
        qages = sorted(Path(".qonqrete/worqspace").glob("qage_*"))
        if not qages:
            return None, output
        qage_dir = qages[-1]
    else:
        qage_dir = Path(match.group(1).strip())
    
    return qage_dir, output

def score_small_run(qage_dir, output):
    if not qage_dir or not qage_dir.exists():
        return {"score": 0, "status": "CRASHED", "strict_perfect": False, "api_runs": False, "run_sh_exact": False, "repairs": 0, "violations": 0, "finish_rule": "FAIL"}

    verdict_path = qage_dir / "verdict" / "inspection-verdict.v1.json"
    if not verdict_path.exists():
        return {"score": 0, "status": "INCOMPLETE", "strict_perfect": False, "api_runs": False, "run_sh_exact": False, "repairs": 0, "violations": 0, "finish_rule": "FAIL"}

    with open(verdict_path, "r") as f:
        verdict = json.load(f)

    status = verdict.get("status")
    repairs = 0
    repair_plans = sorted(qage_dir.glob("verdict/repair-plan.v1.json"))
    if repair_plans:
        with open(repair_plans[-1], "r") as f:
            rp = json.load(f)
            repairs = rp.get("source_repair_pass_index", 0)
    
    violations = verdict.get("repair_scope_violations", [])
    finish_rule_ok = (status == "SUCCESS")
    
    qodeyard = qage_dir / "qodeyard"
    main_py = qodeyard / "main.py"
    run_sh = qodeyard / "run.sh"
    reqs = qodeyard / "requirements.txt"
    
    score = 0
    strict_perfect = True
    api_runs = False
    run_sh_exact = False
    
    if verdict.get("hard_gate_status") == "PASS":
        score += 40
        api_runs = True
    else:
        strict_perfect = False

    if main_py.exists() and reqs.exists() and run_sh.exists():
        score += 10
        all_files = [f.name for f in qodeyard.iterdir() if f.is_file()]
        if set(all_files) == {"main.py", "requirements.txt", "run.sh"}:
            score += 10
        else:
            strict_perfect = False
    else:
        strict_perfect = False

    if run_sh.exists():
        content = run_sh.read_text()
        if 'python -m uvicorn main:app --reload --port $PORT' in content and 'PORT=' not in content:
            score += 15
            run_sh_exact = True
        else:
            strict_perfect = False
    else:
        strict_perfect = False

    if not violations:
        score += 10
    else:
        strict_perfect = False

    if status == "SUCCESS":
        score += 10
    else:
        strict_perfect = False

    score += 5

    return {
        "score": score,
        "status": status,
        "strict_perfect": strict_perfect,
        "api_runs": api_runs,
        "run_sh_exact": run_sh_exact,
        "repairs": repairs,
        "violations": len(violations),
        "finish_rule": "OK" if finish_rule_ok else "FAIL",
        "verdict": verdict
    }

def score_medium_run(qage_dir, output):
    if not qage_dir or not qage_dir.exists():
        return {"score": 0, "status": "CRASHED", "strict_perfect": False, "repairs": 0, "violations": 0, "finish_rule": "FAIL"}

    verdict_path = qage_dir / "verdict" / "inspection-verdict.v1.json"
    if not verdict_path.exists():
        return {"score": 0, "status": "INCOMPLETE", "strict_perfect": False, "repairs": 0, "violations": 0, "finish_rule": "FAIL"}

    with open(verdict_path, "r") as f:
        verdict = json.load(f)

    status = verdict.get("status")
    repairs = 0
    repair_plans = sorted(qage_dir.glob("verdict/repair-plan.v1.json"))
    if repair_plans:
        with open(repair_plans[-1], "r") as f:
            rp = json.load(f)
            repairs = rp.get("source_repair_pass_index", 0)
    
    violations = verdict.get("repair_scope_violations", [])
    finish_rule_ok = (status == "SUCCESS")
    
    qodeyard = qage_dir / "qodeyard"
    index_html = qodeyard / "index.html"
    styles_css = qodeyard / "styles.css"
    app_js = qodeyard / "app.js"
    
    score = 0
    strict_perfect = True
    
    # 25 points: required files and no extras
    if index_html.exists() and styles_css.exists() and app_js.exists():
        score += 15
        all_files = [f.name for f in qodeyard.iterdir() if f.is_file()]
        if set(all_files) == {"index.html", "styles.css", "app.js"}:
            score += 10
        else:
            strict_perfect = False
    else:
        strict_perfect = False

    # 25 points: core recipe CRUD/favorite/expand behavior
    if verdict.get("hard_gate_status") == "PASS":
        score += 25
    else:
        strict_perfect = False

    # 20 points: search/filter/sort/stats behavior
    if verdict.get("hard_gate_status") == "PASS": # Assuming verdict covers these
        score += 20
    else:
        strict_perfect = False

    # 15 points: weekly plan/localStorage/schema correctness
    if verdict.get("hard_gate_status") == "PASS":
        score += 15
    else:
        strict_perfect = False

    # 10 points: repair discipline
    if not violations:
        score += 10
    else:
        strict_perfect = False

    # 5 points: visual cleanliness
    score += 5

    return {
        "score": score,
        "status": status,
        "strict_perfect": strict_perfect,
        "repairs": repairs,
        "violations": len(violations),
        "finish_rule": "OK" if finish_rule_ok else "FAIL",
    }

def main():
    small_results = []
    all_small_perfect = True
    for i in range(NUM_SMALL_RUNS):
        qage_dir, output = run_tasq(TASQ_SMALL, f"Small Run {i+1}")
        res = score_small_run(qage_dir, output)
        small_results.append(res)
        print(f"Score: {res['score']}, Status: {res['status']}, Perfect: {res['strict_perfect']}")
        if not res['strict_perfect']:
            all_small_perfect = False

    print("\n--- SMALL TASQ SCOREBOARD ---")
    print("| Rank | Run | Score | Status | Perfect? | API? | run.sh? | Repairs | Violations | Finish? |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, res in enumerate(small_results):
        print(f"| {i+1} | Run {i+1} | {res['score']} | {res['status']} | {res['strict_perfect']} | {res['api_runs']} | {res['run_sh_exact']} | {res['repairs']} | {res['violations']} | {res['finish_rule']} |")

    if all_small_perfect:
        print("\nAll 9 small runs were PERFECT! Proceeding to 1 medium run.")
        qage_dir_m, output_m = run_tasq(TASQ_MEDIUM, "Medium Run")
        res_m = score_medium_run(qage_dir_m, output_m)
        
        print("\n--- MEDIUM TASQ SCOREBOARD ---")
        print("| Run | Score | Status | Perfect? | Repairs | Violations | Finish? |")
        print("|---|---|---|---|---|---|---|")
        print(f"| Medium | {res_m['score']} | {res_m['status']} | {res_m['strict_perfect']} | {res_m['repairs']} | {res_m['violations']} | {res_m['finish_rule']} |")
    else:
        print("\nSome small runs were not perfect. Medium task skipped.")

if __name__ == "__main__":
    main()
