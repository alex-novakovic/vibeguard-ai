import json
import logging
# from agent.exceptions import ModelTimeout, RateLimitReached
from agent.prompts.suggestion_prompt import SUGGESTION_PROMPT
import asyncio
from data.state import ProjectState
from agent.agent_utils import calculate_remaining_minutes
from agent.config import CONVERSATION_MODEL, client


logger = logging.getLogger(__name__)


async def suggest_next_task(project_state: ProjectState) -> dict:
    vision = project_state.vision_doc
    log = project_state.feature_log
    features = log["features"] # dict {"F001": { "name":,"status":,"cycles":,"drift_events":}...
    
    # identify completed features
    completed_ids = {
        feature_id for feature_id, feature_data in features.items()
        if feature_data["status"] == "complete"
    }

    # filter ready tasks
    ready_tasks = []
    for item in vision.backlog:
        if item.id in completed_ids:
            print(f"Skipping {item.id} (already complete)" )
            continue

        # all dependencies must be complete for this task to be ready
        deps_met = all(
        features.get(dep_id, {}).get("status") == "complete"
        for dep_id in item.dependencies
      )

        if deps_met:
            ready_tasks.append({
                "id": item.id,
                "name": item.name,
                "priority": item.priority,
                "description": item.description,
                "estimatedMinutes": item.estimatedMinutes,
                "confidence": item.confidence,
                "scopeFlag": item.scopeFlag,
                "scopeFlagReason": item.scopeFlagReason,
            })

    if not ready_tasks:
        return {
            "feature_id": None,
            "feature_name": "No tasks available",
            "reason": "All features are complete or blocked by dependencies."
        }

    # build single context dict matching {context} in prompt
    context = {
    # from VisionDoc
    "projectName": vision.projectName,
    "visionStatement": vision.visionStatement,
    "successCriteria": vision.successCriteria,
    "experienceLevel": vision.experienceLevel,
    "availableTimeHours": vision.availableTimeHours,
    "constraints": vision.constraints,
    
    # calculated
    "remaining_budget_minutes": calculate_remaining_minutes(vision, log),
    
    # from feature log — critical for dependency checking
    
    "completed_features": [fid for fid, f in features.items() if f["status"] == "complete"],
    "in_progress_features": [fid for fid, f in features.items() if f["status"] == "in_progress"],

    "available_to_start_now": [t["id"] for t in ready_tasks],
    
    # backlog with full detail
    "backlog": [
    {
        **item.model_dump(),
        "status": (
            "complete" if item.id in completed_ids
            else "in_progress" if item.id == project_state.active_feature_id
            else "to_do"
            )
    } for item in vision.backlog],
   }

    filled_prompt = SUGGESTION_PROMPT.replace(
        "{context}", json.dumps(context, indent=2)
    )

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": filled_prompt}],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        usage = response.usage
        token_count = usage.total_tokens if usage else 0

        raw = response.choices[0].message.content
        print("AI Suggestion Response:", raw)
        
        # 2. Parse the JSON and inject the token count
        result = json.loads(raw)
        result["tokens"] = token_count
        
        return result

    except Exception as e:
        logger.error(f"Failed to get suggestion: {e}")
        first = ready_tasks[0]
        return {
            "feature_id": first["id"],
            "feature_name": first["name"],
            "reason": "Suggested based on backlog priority (AI reasoning unavailable).",
            "tokens": 0 # Default to 0 on failure
        }