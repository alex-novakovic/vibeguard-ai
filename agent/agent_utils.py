import os
import asyncio
from openai import OpenAI
import logging
from agent.prompts.guardian_prompt import GUARDIAN_PROMPT

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("GuardianPhase")


COMPLETE_SIGNALS = [
    "done", "finished", "completed", "complete",
    "shipped", "deployed", "merged", "closed",
    "i finished", "i'm done", "it's done", "its done",
    "feature done", "feature complete", "feature finished",
    "wrapped up", "wrapped it up", "checked it off",
]

CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "google/gemini-2.0-flash-lite-001")

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

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
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        # Clean the output string
        prediction = response.choices[0].message.content.strip().upper()
        
        # VALIDATION GUARDRAIL:
        # If the LLM hallucinates a new category, default to CHAT
        return prediction if prediction in CATEGORIES else "CHAT"

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return "CHAT"

async def generate_guardian_response(project_state, user_msg, skill_output):
    # 1. Prepare the dynamic context
    formatted_prompt = GUARDIAN_PROMPT.format(
        vision_statement=project_state.vision_doc.visionStatement,
        success_criteria=", ".join(project_state.vision_doc.successCriteria),
        active_task=project_state.active_feature_id or "No active task. Ready for a suggestion!"
    )

    # 2. Call the LLM
    messages = [
        {"role": "system", "content": formatted_prompt},
        {"role": "user", "content": f"Internal Skill Data: {skill_output}\n\nUser Message: {user_msg}"}
    ]

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=CONVERSATION_MODEL,
            messages=messages,
            temperature=0.7 # A bit of "human" variance for the voice
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"I'm here, but my voice module failed. (Error: {e})"

def calculate_remaining_minutes(vision_doc, feature_log) -> int:
    total_budget = vision_doc.availableTimeHours * 60
    spent = sum(
        sum(cycle.get("durationMinutes", 0) for cycle in feature.cycles)
        for feature in feature_log
    )
    return max(0, total_budget - spent)