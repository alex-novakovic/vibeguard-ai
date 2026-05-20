import json
import asyncio
import os
from data.schemas import VisionDoc, BacklogItem
from data.state import ProjectState
from agent.drift import check_drift, evaluate_drift_context_sufficiency


def load_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)


def build_project_state_for_drift(case: dict) -> tuple[ProjectState, str]:
    """Builds a minimal ProjectState and active_feature_id from a sufficiency test case."""
    active_feature_id = case["active_feature_id"]

    backlog_item = BacklogItem(
        id=active_feature_id,
        name=case["feature_name"],
        description=case["feature_description"],
        priority="high",
        status="in_progress",
        estimatedMinutes=60,
        dependencies=[],
        confidence="high",
        scopeFlag=False,
    )

    vision_doc = VisionDoc(
        createdAt="2026-01-01T00:00:00+00:00",
        projectName="EvalProject",
        visionStatement="Eval project",
        targetUser="Developer",
        problemStatement="Eval",
        successCriteria="Eval",
        availableTimeHours=8,
        techStack=[],
        externalDependencies=[],
        niceToHave=[],
        backlog=[backlog_item],
    )

    project_state = ProjectState(
        vision_doc=vision_doc,
        feature_log={
            "features": {
                active_feature_id: {
                    "name": case["feature_name"],
                    "status": "in_progress",
                    "cycles": [],
                    "drift_events": [],
                }
            }
        },
    )

    return project_state, active_feature_id


async def run_drift_eval(cases: list) -> list:
    results = []
    correct = 0

    for case in cases:
        try:
            result = await check_drift(
                planned_feature=case["planned_feature"],
                actual_work=case["actual_work"],
                vision_context=case["vision_context"],
            )
        except Exception as e:
            results.append({
                "id":       case["id"],
                "passed":   False,
                "expected_is_drifted": case["expected_is_drifted"],
                "got_is_drifted":      None,
                "expected_severity":   case["expected_severity"],
                "got_severity":        None,
                "feedback":  None,
                "tokens":    0,
                "error":     str(e),
            })
            continue

        passed = result.get("is_drifted") == case["expected_is_drifted"]
        if passed:
            correct += 1

        results.append({
            "id":                  case["id"],
            "description":         case["description"],
            "passed":              passed,
            "expected_is_drifted": case["expected_is_drifted"],
            "got_is_drifted":      result.get("is_drifted"),
            "expected_severity":   case["expected_severity"],
            "got_severity":        result.get("severity"),
            "feedback":            result.get("feedback"),
            "tokens":              result.get("tokens", 0),
        })

        status = "✅" if passed else "❌"
        print(f"{status} {case['id']}: expected is_drifted={case['expected_is_drifted']}, got={result.get('is_drifted')} (severity: {result.get('severity')})")
        print(f"   {case['description']}")
        print(f"   feedback: {result.get('feedback')}")
        print()

    return results, correct


async def run_drift_sufficiency_eval(cases: list) -> list:
    results = []
    correct = 0

    for case in cases:
        project_state, active_feature_id = build_project_state_for_drift(case)

        try:
            prediction, tokens = await evaluate_drift_context_sufficiency(
                gathered_text=case["gathered_text"],
                project_state=project_state,
                active_feature_id=active_feature_id,
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

        passed = prediction == case["expected"]
        if passed:
            correct += 1

        results.append({
            "id":          case["id"],
            "description": case["description"],
            "passed":      passed,
            "expected":    case["expected"],
            "got":         prediction,
            "tokens":      tokens,
        })

        status = "✅" if passed else "❌"
        print(f"{status} {case['id']}: expected={case['expected']}, got={prediction}")
        print(f"   {case['description']}")
        print()

    return results, correct


async def run_eval():
    all_cases = load_cases("tests/eval/data/drift_test_cases.json")

    drift_cases = all_cases["drift_test_cases"]
    sufficiency_cases = all_cases["drift_sufficiency_test_cases"]

    print("=" * 40)
    print("DRIFT CHECK EVAL")
    print("=" * 40)
    drift_results, drift_correct = await run_drift_eval(drift_cases)

    print("=" * 40)
    print("DRIFT SUFFICIENCY EVAL")
    print("=" * 40)
    suf_results, suf_correct = await run_drift_sufficiency_eval(sufficiency_cases)

    drift_accuracy = drift_correct / len(drift_cases) if drift_cases else 0
    suf_accuracy = suf_correct / len(sufficiency_cases) if sufficiency_cases else 0
    total_tokens = sum(r["tokens"] for r in drift_results + suf_results)

    summary = {
        "drift_check": {
            "total_cases": len(drift_cases),
            "correct":     drift_correct,
            "accuracy":    round(drift_accuracy, 3),
            "results":     drift_results,
        },
        "drift_sufficiency": {
            "total_cases": len(sufficiency_cases),
            "correct":     suf_correct,
            "accuracy":    round(suf_accuracy, 3),
            "results":     suf_results,
        },
        "total_tokens": total_tokens,
    }

    os.makedirs("tests/eval/results", exist_ok=True)

    with open("tests/eval/results/drift_eval_results.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 40)
    print(f"Drift check accuracy:       {drift_correct}/{len(drift_cases)} ({drift_accuracy:.1%})")
    print(f"Sufficiency accuracy:        {suf_correct}/{len(sufficiency_cases)} ({suf_accuracy:.1%})")
    print(f"Total tokens:                {total_tokens}")
    print(f"Results saved to tests/eval/results/drift_eval_results.json")


if __name__ == "__main__":
    asyncio.run(run_eval())