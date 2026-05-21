import json
import asyncio
from types import SimpleNamespace
from data.db import init_db
from data.schemas import VisionDoc
from data.state import ProjectState
from agent.suggestion import suggest_next_task
import os


def load_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)


def _dict_to_feature_log(d: dict) -> list:
    return [
        SimpleNamespace(feature_id=fid, name=f["name"], status=f["status"], cycle=None)
        for fid, f in d.get("features", {}).items()
    ]


def build_project_state(case: dict) -> ProjectState:
    raw = case["project_state"]
    vision_raw = raw["vision_doc"]
    vision_raw.setdefault("user_id", "eval-user")
    vision_doc = VisionDoc(**vision_raw)
    feature_log = _dict_to_feature_log(raw["feature_log"])
    return ProjectState(vision_doc=vision_doc, feature_log=feature_log)


async def run_eval():
    await init_db()
    cases = load_cases("tests/eval/data/suggest_next_task_cases.json")

    results = []
    correct = 0

    for case in cases:
        project_state = build_project_state(case)

        try:
            result = await suggest_next_task(project_state)
        except Exception as e:
            results.append({
                "id":       case["id"],
                "passed":   False,
                "expected": case["expected_feature_id"],
                "got":      None,
                "tokens":   0,
                "error":    str(e)
            })
            continue

        passed = result.get("feature_id") == case["expected_feature_id"]
        if passed:
            correct += 1

        results.append({
            "id":          case["id"],
            "description": case["description"],
            "passed":      passed,
            "expected":    case["expected_feature_id"],
            "got":         result.get("feature_id"),
            "reason":      result.get("reason"),
            "tokens":      result.get("tokens", 0),
        })

        status = "✅" if passed else "❌"
        print(f"{status} {case['id']}: expected {case['expected_feature_id']}, got {result.get('feature_id')}")
        print(f"   reason: {result.get('reason')}")
        print()

    accuracy = correct / len(cases) if cases else 0
    total_tokens = sum(r["tokens"] for r in results)

    summary = {
        "total_cases":   len(cases),
        "correct":       correct,
        "accuracy":      round(accuracy, 3),
        "total_tokens":  total_tokens,
        "results":       results
    }

    os.makedirs("tests/eval/results", exist_ok=True)
    with open("tests/eval/results/suggest_next_task_results.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"════════════════════════════════")
    print(f"Accuracy:     {correct}/{len(cases)} ({accuracy:.1%})")
    print(f"Total tokens: {total_tokens}")
    print(f"Results saved to tests/eval/results/suggest_next_task_results.json")


if __name__ == "__main__":
    asyncio.run(run_eval())
