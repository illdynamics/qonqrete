import os
import json
from pathlib import Path

def score_qonstruction(path: Path, name: str):
    verdict_path = path / "qage" / "verdict" / "inspection-verdict.v1.json"
    if not verdict_path.exists():
        return {"name": name, "status": "INCOMPLETE", "score": 0, "perfect": False, "error": "No verdict"}

    with open(verdict_path) as f:
        verdict = json.load(f)

    status = verdict.get("status")
    hard_gate_status = verdict.get("hard_gate_status")
    repairs = verdict.get("source_repair_pass_index", 0) # approximation, better to read repair_plan
    violations = len(verdict.get("repair_scope_violations", []))

    qodeyard = path / "qage" / "qodeyard"
    main_py = qodeyard / "main.py"
    run_sh = qodeyard / "run.sh"
    reqs = qodeyard / "requirements.txt"

    score = 0
    if hard_gate_status == "PASS":
        score += 40

    if main_py.exists() and reqs.exists() and run_sh.exists():
        score += 10
        files = list(qodeyard.iterdir())
        if len(files) <= 5:
            score += 10

    run_sh_exact = False
    if run_sh.exists():
        content = run_sh.read_text()
        if "python -m uvicorn main:app --reload --port $PORT" in content and "PORT=" not in content:
            score += 15
            run_sh_exact = True

    if violations == 0:
        score += 10

    if status == "SUCCESS" or status == "COMPLETED" or verdict.get("task_outcome") == "PASS":
        score += 10

    score += 5

    strict_perfect = (score >= 100 and hard_gate_status == "PASS" and run_sh_exact and violations == 0)
    
    return {
        "name": name,
        "score": score,
        "status": status,
        "perfect": strict_perfect,
        "api_runs": hard_gate_status == "PASS",
        "run_sh_exact": run_sh_exact,
        "repairs": repairs,
        "violations": violations,
        "finish_rule": "OK" if score >= 90 else "FAIL",
        "diagnosis": verdict.get("completion_assessment", "")[:50] + "..."
    }

def main():
    root = Path(".qonqrete/worqspace/qonstructions")
    results = []
    all_perfect = True
    
    for i in range(1, 10):
        name = f"small-test-{i}"
        path = root / name
        res = score_qonstruction(path, name)
        results.append(res)
        if not res.get("perfect", False):
            all_perfect = False

    print("\n--- SMALL TASQ SCOREBOARD ---")
    print("| Rank | Run | Score | Status | Perfect? | API? | run.sh? | Repairs | Violations | Finish? | Diagnosis |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, res in enumerate(results):
        print(f"| {i+1} | {res['name']} | {res.get('score')} | {res.get('status')} | {res.get('perfect')} | {res.get('api_runs')} | {res.get('run_sh_exact')} | {res.get('repairs')} | {res.get('violations')} | {res.get('finish_rule')} | {res.get('diagnosis')} |")

    print(f"\nAll perfect: {all_perfect}")

if __name__ == "__main__":
    main()