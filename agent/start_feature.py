import json
import logging
from agent.config import CONVERSATION_MODEL, client
from data.state import ProjectState

logger = logging.getLogger(__name__)

async def extract_feature_id_from_msg(
    user_msg: str, 
    feature_log: dict, 
    history: list
) -> dict:
    """
    Identifies the Feature ID based on the user message, the available features,
    and a slice of history.
    """
    
    # filter out completed, build short list for the LLM
    short_log = [{"id": f.feature_id, "name": f.name} for f in feature_log if f.status != "complete"]

    # 2. Slice the history to exactly 10
    # recent_history = history[-10:] if history else []
    active_feature_id = next((f.feature_id for f in feature_log if f.status == "in_progress"), None)

    active_feature_info = (
    f"IMPORTANT: Feature {active_feature_id} is already IN PROGRESS. "
    f"If the user says anything generic like 'okay', 'yes', 'let's go', 'sure' — "
    f"they mean they want to CONTINUE {active_feature_id}, not start a new one. "
    f"Only pick a different feature if the user explicitly names it."
   ) if active_feature_id else "No feature is currently in progress."

    extraction_prompt = f"""
    Identify the Feature ID the user wants to START.

    {active_feature_info}
    
    BACKLOG: {json.dumps(short_log)}
    CONTEXT: {json.dumps(history)}
    USER: "{user_msg}"
    
    Return ONLY a single JSON object.
    Do NOT return a list.
    Do NOT wrap in array.
    Format: {{"feature_id": "ID", "reason": "why"}}
    """

    try:
        response = await client.chat.completions.create (
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": extraction_prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        result = json.loads(response.choices[0].message.content)
        logger.debug(f"Extraction Result: {result}")

        result = {
        "feature_id": result.get("feature_id"),
        "reason": result.get("reason"),
        "tokens": response.usage.total_tokens
      }
        
        return result

    except Exception as e:
        logger.error(f"Extraction Error: {e}")
        return {"feature_id": None, "reason": "Error", "tokens": 0}

async def start_feature(project_state: ProjectState, feature_id: str) -> dict:
    feature = next((f for f in project_state.feature_log if f.feature_id == feature_id), None)
    
    if not feature:
        return {"flag": "ERROR", "message": f"Feature {feature_id} not found in feature log."}
    
    if feature.status == "in_progress":
        project_state.previous_feature_id = feature_id
        project_state.active_feature_id = feature_id
        return {"flag": "RESUMING", "message": f"Feature {feature_id} is already active, resuming."}

    project_state.previous_feature_id = None
    project_state.active_feature_id = feature_id

    return {"flag": "START", "message": f"Feature {feature_id} marked as started."}