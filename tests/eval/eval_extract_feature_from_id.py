import json
import asyncio
from agent.start_feature import extract_feature_id_from_msg
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")


def load_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)


async def run_eval():
    cases = load_cases("tests/eval/data/extract_feature_from_id_cases.json")

    results = []
    correct = 0

    for case in cases:
        inp = case["input"]

        try:
            result = await extract_feature_id_from_msg(
                user_msg=inp["user_msg"],
                feature_log=inp["feature_log"],
                history=inp["history"],
            )
        except Exception as e:
            results.append({
                "id":       case["id"],
                "passed":   False,
                "expected": case["expected_feature_id"],
                "got":      None,
                "tokens":   0,
                "error":    str(e),
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
        print(f"   {case['description']}")
        print(f"   reason: {result.get('reason')}")
        print()

    accuracy = correct / len(cases) if cases else 0
    total_tokens = sum(r["tokens"] for r in results)

    summary = {
        "total_cases":  len(cases),
        "correct":      correct,
        "accuracy":     round(accuracy, 3),
        "total_tokens": total_tokens,
        "results":      results,
    }
    
    os.makedirs("tests/eval/results", exist_ok=True)

    with open("tests/eval/results/extract_feature_from_id_results.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"════════════════════════════════")
    print(f"Accuracy:     {correct}/{len(cases)} ({accuracy:.1%})")
    print(f"Total tokens: {total_tokens}")
    print(f"Results saved to tests/eval/results/extract_feature_id_results.json")


if __name__ == "__main__":
    asyncio.run(run_eval())