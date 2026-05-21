import logging
from agent.prompts.guardian_prompt import GUARDIAN_PROMPT
from agent.config import CONVERSATION_MODEL, client
from agent.prompts.classify_guardian_intent_prompt import build_guardian_intent_prompt
import json

logger = logging.getLogger(__name__)

# is_returning = True only on first message after refresh
async def classify_guardian_intent(user_message: str, active_feature_id: str | None = None, last_assistant_msg: str | None = None, is_returning: bool = False) -> dict:
    CATEGORIES = ["SUGGEST", "START", "COMPLETE", "CHAT"]
    
    prompt = build_guardian_intent_prompt(active_feature_id, last_assistant_msg, is_returning, user_message)

    try:
        response = await client.chat.completions.create(
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        usage = response.usage
        prediction = response.choices[0].message.content.strip().upper()

        return {
            "prediction": prediction if prediction in CATEGORIES else "CHAT",
            "tokens": usage.total_tokens if usage else 0
        }

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return {
            "prediction": "CHAT",
            "tokens": 0
        }

async def generate_guardian_response(project_state, user_msg, skill_output, history: list):
    #Prepare the dynamic context (unchanged)
    formatted_prompt = GUARDIAN_PROMPT.format(
        vision_statement=project_state.vision_doc.visionStatement,
        success_criteria=", ".join(project_state.vision_doc.successCriteria),
        active_task=project_state.active_feature_id or "No active task.",
        backlog=json.dumps([{"id": item.id, "name": item.name, "status": item.status} for item in project_state.vision_doc.backlog])
    )
    #Start with System
    messages = [{"role": "system", "content": formatted_prompt}]
    messages.extend(history[-10:])
    messages.append({
        "role": "user", 
        "content": f"Internal Skill Data: {skill_output}\n\nUser Message: {user_msg}"
    })

    try:
        response = await client.chat.completions.create (
            model=CONVERSATION_MODEL,
            messages=messages,
            temperature=0.7 
        )
        
        usage = response.usage
        return {
            "text": response.choices[0].message.content.strip(),
            "tokens": usage.total_tokens if usage else 0
        }
    except Exception as e:
        logger.error(f"Guardian Response Error: {e}")
        return {"text": "I encountered an error processing that. Could you try again?", "tokens": 0}


def calculate_remaining_minutes(vision_doc, feature_log) -> int:
    total_budget = vision_doc.availableTimeHours * 60
    
    spent = 0
    for feature in feature_log:
        cycle = feature.cycle
        if cycle and cycle.started_at and cycle.completed_at:
            delta = cycle.completed_at - cycle.started_at
            spent += delta.total_seconds() / 60

    return max(0, total_budget - int(spent))