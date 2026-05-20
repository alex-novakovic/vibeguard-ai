import asyncio
import json
import os
from datetime import datetime
from agent.scoping import ScopingSession


def load_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)["scoping_test_cases"]


def check_backlog(vision_doc, expected_backlog: list) -> tuple[int, list[str]]:
    """Returns (correct_count, list_of_failures)."""
    failures = []
    correct = 0

    for i, expected_item in enumerate(expected_backlog):
        actual_item = None
        for item in vision_doc.backlog:
            if expected_item["name_contains"].lower() in item.name.lower():
                actual_item = item
                break

        if actual_item is None:
            failures.append(f"  item[{i}]: no backlog item with name containing '{expected_item['name_contains']}'")
            continue

        item_ok = True
        if actual_item.priority != expected_item["priority"]:
            failures.append(f"  item '{actual_item.name}': priority expected={expected_item['priority']} got={actual_item.priority}")
            item_ok = False
        if actual_item.confidence != expected_item["confidence"]:
            failures.append(f"  item '{actual_item.name}': confidence expected={expected_item['confidence']} got={actual_item.confidence}")
            item_ok = False
        if actual_item.scopeFlag != expected_item["scopeFlag"]:
            failures.append(f"  item '{actual_item.name}': scopeFlag expected={expected_item['scopeFlag']} got={actual_item.scopeFlag}")
            item_ok = False

        if item_ok:
            correct += 1

    return correct, failures


async def run_scoping_eval(cases: list) -> list:
    print("\n" + "=" * 50)
    print("SCOPING SESSION (PARSING) EVAL")
    print("=" * 50 + "\n")

    results = []
    total_passed = 0

    for case in cases:
        session = ScopingSession()
        session.chat_messages = case["messages"]

        try:
            vision_doc = await session.scoping_session()
        except Exception as e:
            results.append({
                "id": case["id"],
                "description": case["description"],
                "passed": False,
                "error": str(e),
                "failures": [],
                "tokens": session.total_tokens,
            })
            print(f"❌ [{case['id']}] {case['description']}")
            print(f"   ERROR: {e}\n")
            continue

        exp = case["expected"]
        failures = []

        # projectName
        if exp["projectName"].lower() not in vision_doc.projectName.lower():
            failures.append(f"  projectName: expected to contain '{exp['projectName']}', got '{vision_doc.projectName}'")

        # availableTime null check
        if exp["availableTime_is_null"] and vision_doc.availableTime is not None:
            failures.append(f"  availableTime: expected null, got '{vision_doc.availableTime}'")
        elif not exp["availableTime_is_null"] and vision_doc.availableTime is None:
            failures.append(f"  availableTime: expected non-null, got null")

        # availableTimeHours — allow ±30% tolerance
        if "availableTimeHours" in exp:
            expected_hours = exp["availableTimeHours"]
            got_hours = vision_doc.availableTimeHours
            tolerance = max(1, expected_hours * 0.30)
            if abs(got_hours - expected_hours) > tolerance:
                failures.append(f"  availableTimeHours: expected ~{expected_hours}, got {got_hours}")

        # backlog count
        if len(vision_doc.backlog) != exp["backlog_count"]:
            failures.append(f"  backlog_count: expected {exp['backlog_count']}, got {len(vision_doc.backlog)}")

        # backlog item checks
        backlog_correct, backlog_failures = check_backlog(vision_doc, exp["backlog"])
        failures.extend(backlog_failures)

        # niceToHave count
        if len(vision_doc.niceToHave) != exp["nice_to_have_count"]:
            failures.append(f"  nice_to_have_count: expected {exp['nice_to_have_count']}, got {len(vision_doc.niceToHave)}")

        # techStack
        if "tech_stack_contains" in exp:
            for tech in exp["tech_stack_contains"]:
                if not any(tech.lower() in t.lower() for t in vision_doc.techStack):
                    failures.append(f"  techStack: expected '{tech}' to be present, got {vision_doc.techStack}")

        passed = len(failures) == 0
        if passed:
            total_passed += 1

        status = "✅" if passed else "❌"
        print(f"{status} [{case['id']}] {case['description']}")
        if failures:
            for f in failures:
                print(f)
        else:
            print(f"   projectName={vision_doc.projectName}, backlog={len(vision_doc.backlog)} items, niceToHave={len(vision_doc.niceToHave)}")
        print(f"   tokens={session.total_tokens}")
        print()

        results.append({
            "id": case["id"],
            "description": case["description"],
            "passed": passed,
            "failures": failures,
            "projectName": vision_doc.projectName,
            "backlog_count": len(vision_doc.backlog),
            "nice_to_have_count": len(vision_doc.niceToHave),
            "tokens": session.total_tokens,
            "notes": case.get("notes", ""),
        })

    accuracy = total_passed / len(cases) if cases else 0
    print(f"SCOPING ACCURACY: {total_passed}/{len(cases)} ({accuracy:.0%})\n")
    return results, total_passed


async def main():
    cases = load_cases("tests/eval/data/scoping_test_cases.json")
    results, total_passed = await run_scoping_eval(cases)

    accuracy = total_passed / len(cases) if cases else 0
    total_tokens = sum(r.get("tokens", 0) for r in results)

    report = {
        "timestamp": datetime.now().isoformat(),
        "scoping": {
            "total_cases": len(cases),
            "correct": total_passed,
            "accuracy": round(accuracy, 3),
            "results": results,
        },
        "total_tokens": total_tokens,
    }

    os.makedirs("tests/eval/results", exist_ok=True)
    with open("tests/eval/results/scoping_eval_results.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Results saved to tests/eval/results/scoping_eval_results.json")


if __name__ == "__main__":
    asyncio.run(main())
