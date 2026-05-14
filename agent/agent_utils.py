import asyncio
import logging
from agent.prompts.guardian_prompt import GUARDIAN_PROMPT
from agent.config import CONVERSATION_MODEL, client
from datetime import datetime


logger = logging.getLogger(__name__)


async def classify_guardian_intent(user_message: str) -> str:
    # We define the allowed set here to use for both the prompt and the validation
     
    CATEGORIES = ["SUGGEST", "START", "COMPLETE", "CHAT"] 
    prompt = f"""
    You are the Intent Router for VibeGuard, a project management AI. 
    Analyze the user's message and categorize it into ONE of these buckets:

    CATEGORIES & DEFINITIONS:
    - SUGGEST: Use this if the user is asking for direction, feeling lost, requesting a new task, or asking for the 'next move'. 
    - START: Use this if the user is accepting a suggestion, saying "let's go", "okay", "doing this now", or explicitly naming a feature to begin (or when the user agrees to start a task in response to a suggestion).
    - COMPLETE: Use this if the user is reporting progress, claiming something is 'finished', 'done', 'fixed', 'implemented', or 'ready'.
    - CHAT: Use this for anything else—general questions, greetings, feedback, or technical queries that don't involve starting/stopping a task.

    EXAMPLES:
    "sounds good, i'll do it" -> START
    "whats on the menu for today?" -> SUGGEST
    "api is finally pushing data" -> COMPLETE
    "how do i fix a 404 error?" -> CHAT

    User Message: "{user_message}"

    Respond only with the category name (SUGGEST, START, COMPLETE, or CHAT).
    """

    try:
        response = await client.chat.completions.create (
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        usage = response.usage

        # Clean the output string
        prediction = response.choices[0].message.content.strip().upper()
        
        # VALIDATION GUARDRAIL:
        # If the LLM hallucinates a new category, default to CHAT
        return {
            "prediction" : prediction if prediction in CATEGORIES else "CHAT",
            "tokens": usage.total_tokens if usage else 0
}

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return {
            "prediction": "CHAT",
            "tokens": 0
        }

async def generate_guardian_response(project_state, user_msg, skill_output, history: list):
    # 1. Prepare the dynamic context (unchanged)
    formatted_prompt = GUARDIAN_PROMPT.format(
        vision_statement=project_state.vision_doc.visionStatement,
        success_criteria=", ".join(project_state.vision_doc.successCriteria),
        active_task=project_state.active_feature_id or "No active task."
    )

    # 2. Build the message chain
    # Start with System
    messages = [{"role": "system", "content": formatted_prompt}]
    
    # Add the last 10 messages from history (Conversation Memory)
    # We slice [-10:] to keep it efficient
    messages.extend(history[-10:])
    
    # Add the current Turn Data (The "Now")
    # We include skill_output here so the AI knows what the "Skills" found
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
    features = feature_log["features"]
    
    spent = 0
    for feature in features.values():
        for cycle in feature["cycles"]:
            started = cycle.get("started_at")
            completed = cycle.get("completed_at")
            if started and completed:  # only count finished cycles
                delta = datetime.fromisoformat(completed) - datetime.fromisoformat(started)
                spent += delta.total_seconds() / 60

    return max(0, total_budget - int(spent))