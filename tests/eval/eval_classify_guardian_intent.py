import json
import asyncio
from agent.agent_utils import classify_guardian_intent
import sys
import os


sys.stdout.reconfigure(encoding="utf-8")



sys.stdout.reconfigure(encoding="utf-8")



def load_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)


async def run_eval():
    cases = load_cases("tests/eval/data/classify_guardian_intent_cases.json")

    results = []
    correct = 0

    for case in cases:
        inp = case["input"]

        try:
            result = await classify_guardian_intent(
                user_message=inp["user_message"],
                active_feature_id=inp.get("active_feature_id"),
                last_assistant_msg=inp.get("last_assistant_msg"),
                is_returning=inp.get("is_returning", False),
            )
        except Exception as e:
            results.append({
                "id":       case["id"],
                "passed":   False,
                "expected": case["expected"],
                "got":      None,
                "tokens":   0,
                "error":    str(e),
            })
            continue

        passed = result.get("prediction") == case["expected"]
        if passed:
            correct += 1

        results.append({
            "id":          case["id"],
            "description": case["description"],
            "passed":      passed,
            "expected":    case["expected"],
            "got":         result.get("prediction"),
            "tokens":      result.get("tokens", 0),
        })

        status = "✅" if passed else "❌"
        print(f"{status} {case['id']}: expected {case['expected']}, got {result.get('prediction')}")
        print(f"   {case['description']}")
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
    with open("tests/eval/results/classify_guardian_intent_results.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"════════════════════════════════")
    print(f"Accuracy:     {correct}/{len(cases)} ({accuracy:.1%})")
    print(f"Total tokens: {total_tokens}")
    print(f"Results saved to tests/eval/results/classify_guardian_intent_results.json")


if __name__ == "__main__":
    asyncio.run(run_eval())