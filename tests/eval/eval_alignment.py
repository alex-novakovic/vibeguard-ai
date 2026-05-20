# eval/run_eval.py

import asyncio
import json
import os
from datetime import datetime
from agent.complete import vision_alignment_check, evaluate_context_sufficiency
from data.state import ProjectState
from data.schemas import VisionDoc, BacklogItem


def load_test_cases():
    """Loads consolidated test cases from the JSON file."""
    json_path = "test_cases.json"
    
    # Fallback to absolute or relative subfolder paths if script runs within an 'eval' directory
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(__file__), "..", "data/alignment_test_cases.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(__file__), "data/alignment_test_cases.json")
        
    with open(json_path, "r") as f:
        return json.load(f)


async def run_alignment_eval(alignment_cases):
    print("\n=== ALIGNMENT CHECK EVALUATION ===\n")
    results = []
    correct = 0

    for case in alignment_cases:
        result = await vision_alignment_check(
            planned_feature=case["planned_feature"],
            actual_work=case["actual_work"],
            vision_context=case["vision_context"],
        )

        alignment_passed = result["is_aligned"] == case["expected_is_aligned"]
        
        if alignment_passed:
            correct += 1

        results.append({
            "id": case["id"],
            "description": case["description"],
            "expected_alignment": case["expected_is_aligned"],
            "got_alignment": result["is_aligned"],
            "passed": alignment_passed,
            "feedback": result.get("feedback", ""),
            "tokens": result.get("tokens", 0),
            "notes": case["notes"],
        })

        status = "✅" if alignment_passed else "❌"
        print(f"{status} [{case['id']}] {case['description']}")
        print(f"   Alignment -> Expected: {case['expected_is_aligned']} | Got: {result['is_aligned']}")
        print(f"   Feedback:  {result.get('feedback', '')}")
        print()

    accuracy = correct / len(alignment_cases) * 100 if alignment_cases else 0
    print(f"ALIGNMENT ACCURACY: {correct}/{len(alignment_cases)} ({accuracy:.0f}%)\n")
    return results


async def run_sufficiency_eval(sufficiency_cases):
    print("\n=== SUFFICIENCY CHECK EVALUATION ===\n")
    results = []
    correct = 0

    for case in sufficiency_cases:
        # Build strict minimal validation models matching your standard BacklogItem
        mock_backlog_item = BacklogItem(
            id=case["active_feature_id"],
            name=case["feature_name"],
            description=case["feature_description"],
            priority="high",
            status="to_do",
            estimatedMinutes=60,
            dependencies=[],
            confidence="high",
            scopeFlag=False,
            scopeFlagReason=None,
        )
        mock_vision = VisionDoc(
            createdAt="2026-01-01T00:00:00Z",
            projectName="TestProject",
            visionStatement="Test vision",
            targetUser="Developers",
            problemStatement="Test problem",
            availableTime=None,
            availableTimeHours=10,
            experienceLevel="comfortable",
            successCriteria="Test criteria",
            constraints=None,
            techStack=["React"],
            externalDependencies=[],
            niceToHave=[],
            backlog=[mock_backlog_item],
        )
        mock_project_state = ProjectState(
            vision_doc=mock_vision,
            feature_log={"features": {}, "backlog": []}, # Clean fallback initialization 
        )

        result, tokens = await evaluate_context_sufficiency(
            gathered_text=case["gathered_text"],
            project_state=mock_project_state,
            active_feature_id=case["active_feature_id"],
        )

        passed = result == case["expected"]
        if passed:
            correct += 1

        results.append({
            "id": case["id"],
            "description": case["description"],
            "expected": case["expected"],
            "got": result,
            "passed": passed,
            "tokens": tokens,
            "notes": case["notes"],
        })

        status = "✅" if passed else "❌"
        print(f"{status} [{case['id']}] {case['description']}")
        print(f"   Expected: {case['expected']} | Got: {result}")
        print(f"   Tokens: {tokens}")
        print()

    accuracy = correct / len(sufficiency_cases) * 100 if sufficiency_cases else 0
    print(f"SUFFICIENCY ACCURACY: {correct}/{len(sufficiency_cases)} ({accuracy:.0f}%)\n")
    return results


async def main():
    # 1. Load data from target centralized file
    test_data = load_test_cases()
    
    # 2. Extract specific arrays
    alignment_cases = test_data.get("alignment_test_cases", [])
    sufficiency_cases = test_data.get("sufficiency_test_cases", [])

    # 3. Execute evaluation sequences
    alignment_results = await run_alignment_eval(alignment_cases)
    sufficiency_results = await run_sufficiency_eval(sufficiency_cases)

    # 4. Generate automated metric summary reports
    report = {
        "timestamp": datetime.now().isoformat(),
        "alignment": {
            "accuracy": sum(1 for r in alignment_results if r["passed"]) / len(alignment_results) if alignment_results else 0,
            "results": alignment_results,
        },
        "sufficiency": {
            "accuracy": sum(1 for r in sufficiency_results if r["passed"]) / len(sufficiency_results) if sufficiency_results else 0,
            "results": sufficiency_results,
        }
    }

    # Ensure targeted sub-directory outputs exist dynamically
    os.makedirs("eval", exist_ok=True)
    with open("tests/eval/results/alignment_results.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("Report successfully updated and saved to eval/eval_report.json")


if __name__ == "__main__":
    asyncio.run(main())