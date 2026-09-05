
import subprocess
import json
import os
import sys
import time
from pathlib import Path

# Config
TASQ_SMALL = ".qonqrete/tasq-small.md"
TASQ_MEDIUM = ".qonqrete/tasq-medium.md"
NUM_RUNS = 9
QONQRETE_SH = "./.qonqrete/qonqrete.sh"

def run_tasq(task_file, label):
    print(f"\n>>> Running {label}...")
    cmd = [QONQRETE_SH, "run", "-f", task_file, "--auto", "--no-sync"]
    # We want to capture the run ID from the output or filesystem
    # Qages are created in .qonqrete/worqspace/qage_...
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    end_time = time.time()
    
    if result.returncode != 0:
        print(f"!!! {label} failed with return code {result.returncode}")
        print(result.stderr)
        return None
    
    # Find the latest qage directory
    worqspace = Path(".qonqrete/worqspace")
    qages = sorted(worqspace.glob("qage_*"), key=os.path.getmtime)
    if not qages:
        print(f"!!! No qage directory found for {label}")
        return None
    
    latest_qage = qages[-1]
    duration = end_time - start_time
    
    return {
        "id": latest_qage.name,
        "path": latest_qage,
        "duration": duration,
        "stdout": result.stdout,
        "stderr": result.stderr
    }

def score_small_run(run_data):
    qage_path = run_data["path"]
    verdict_path = qage_path / "verdict" / "inspection-verdict.v1.json"
    if not verdict_path.exists():
        return {"error": "No verdict found"}
    
    with open(verdict_path) as f:
        verdict = json.load(f)
    
    qodeyard = qage_path / "qodeyard"
    main_py = qodeyard / "main.py"
    run_sh = qodeyard / "run.sh"
    reqs = qodeyard / "requirements.txt"
    
    # Extract metrics
    status = verdict.get("status")
    hard_gate_status = verdict.get("hard_gate_status")
    attempts = len(verdict.get("attempt_ids", [])) # Approximate
    # Actually, repairs is source_repair_pass_index in execution_meta
    repairs = verdict.get("source_repair_pass_index", 0)
    violations = len(verdict.get("repair_scope_violations", []))
    
    score = 0
    # 40 points: runtime/API behavior (using hard_gate_status as proxy)
    if hard_gate_status == "PASS":
        score += 40
    
    # 20 points: exact task contract/files/schema
    if main_py.exists() and reqs.exists() and run_sh.exists():
        score += 10
        # Check no extra files (approximate)
        files = list(qodeyard.iterdir())
        if len(files) <= 5: # main.py, run.sh, requirements.txt + maybe __pycache__ or .DS_Store
            score += 10
            
    # 15 points: run.sh exactness
    run_sh_exact = False
    if run_sh.exists():
        content = run_sh.read_text()
        if "python -m uvicorn main:app --reload --port $PORT" in content and "PORT=" not in content:
            score += 15
            run_sh_exact = True
            
    # 10 points: repair discipline
    if violations == 0:
        score += 10
        
    # 10 points: finish-when-good discipline
    # (If it finished with SUCCESS and no unnecessary repairs)
    if status == "SUCCESS":
        score += 10
        
    # 5 points: code quality
    score += 5
    
    strict_perfect = (score >= 100 and hard_gate_status == "PASS" and run_sh_exact and violations == 0)
    
    return {
        "run": run_data["id"],
        "score": score,
        "status": status,
        "strict_perfect": strict_perfect,
        "api_runs": hard_gate_status == "PASS",
        "run_sh_exact": run_sh_exact,
        "duration": f"{run_data['duration']:.1f}s",
        "repairs": repairs,
        "violations": violations,
        "finish_rule": "OK" if status == "SUCCESS" else "FAIL",
        "diagnosis": verdict.get("completion_assessment", "")[:50] + "..."
    }

def main():
    small_results = []
    all_perfect = True
    
    for i in range(NUM_RUNS):
        run_data = run_tasq(TASQ_SMALL, f"Small Run {i+1}")
        if not run_data:
            print("Aborting experiment due to run failure.")
            return
        
        score = score_small_run(run_data)
        small_results.append(score)
        print(f"Score: {score['score']}, Perfect: {score['strict_perfect']}")
        if not score['strict_perfect']:
            all_perfect = False
            
    # Print Scoreboard
    print("\nWoNQ SCOREBOARD (Small Tasq)")
    print("| Rank | Run | WoNQ score | Final status | Strict perfect pass? | API runs? | run.sh exact? | Duration | Repairs | Locked-file violations | Finish rule behaved? | Main diagnosis |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    sorted_small = sorted(small_results, key=lambda x: x["score"], reverse=True)
    for i, res in enumerate(sorted_small):
        print(f"| {i+1} | {res['run']} | {res['score']} | {res['status']} | {res['strict_perfect']} | {res['api_runs']} | {res['run_sh_exact']} | {res['duration']} | {res['repairs']} | {res['violations']} | {res['finish_rule']} | {res['diagnosis']} |")
        
    if all_perfect:
        print("\nAll 9 small runs were PERFECT! Running 1 medium run...")
        medium_run = run_tasq(TASQ_MEDIUM, "Medium Run")
        if medium_run:
            # Add medium scoring here if needed, or just report basic status
            print(f"Medium run finished: {medium_run['id']}")
    else:
        print("\nNot all small runs were perfect. Skipping medium run.")

if __name__ == "__main__":
    main()
