import logging
from agent.prompts.guardian_prompt import GUARDIAN_PROMPT
from agent.config import CONVERSATION_MODEL, client
from datetime import datetime


logger = logging.getLogger(__name__)


# is_returning = True only on first message after refresh
async def classify_guardian_intent(user_message: str, active_feature_id: str | None = None, last_assistant_msg: str | None = None, is_returning: bool = False) -> dict:
    CATEGORIES = ["SUGGEST", "START", "COMPLETE", "CHAT"]
    active_context = f"Active feature in progress: {active_feature_id}" if active_feature_id else "No active feature."
    
    # replace the PRIORITY OVERRIDE block with this:
    override_rule = """
    ⚠️ PRIORITY OVERRIDE — RETURNING SESSION:
        The user just returned to an existing session with an active feature.
        Their first message is almost certainly just an acknowledgment.
        Return START immediately, no further analysis needed.
        This rule overrides ALL other rules below.
    """ if is_returning else ""

    prompt = f"""
    You are the Intent Router for VibeGuard. Categorize the user's message based on the CURRENT CONTEXT.

    CURRENT PROJECT STATE:
    - {active_context}
    - Last assistant message: "{last_assistant_msg}"

    {override_rule}

    TASK:
    Read the last assistant message carefully. Determine:
    1. Was the assistant proposing a specific action or feature for the user to start? (suggestion_pending = True)
    2. Was it general conversation, a question answer, or a status update? (suggestion_pending = False)

    Then classify the user's reply using these rules:

    CATEGORIES & STRICT RULES:
    1. START: Use this when the user is committing to begin a feature they haven't started yet. This includes:
    - suggestion_pending is True AND user accepts (e.g., "okay", "let's go", "do it", "sure")
    - Active feature exists AND user says they are about to start ("I'll start now", "beginning now", "on it")
    - Do NOT use START if the user is describing work already in progress, asking questions, or reporting plans — that is CHAT.
    2. SUGGEST: User explicitly asks for a new task or direction ("what's next?", "give me something to do").
    3. COMPLETE: User confirms work is done ("finished", "done", "pushed", "deployed", "ready for review").
    4. CHAT: Everything else — questions, acknowledgments when nothing was proposed, technical help.

    EXAMPLES:
    - Last msg proposes F001 + user says "okay" -> START
    - Last msg proposes F001 + user says "actually what about F003?" -> CHAT
    - Last msg proposes F001 + user says "no, suggest something else" -> SUGGEST

    - Last msg is "Welcome back! Your project is loaded." + user says "okay" AND active feature exists -> START
    - Last msg is "Welcome back! Your project is loaded." + user says "okay" AND no active feature -> SUGGEST
    - Last msg is "Welcome back! Your project is loaded." + user says "what should I work on?" -> SUGGEST

    - Last msg answers a question + user says "sounds good" -> CHAT
    - Last msg answers a question + user says "thanks" -> CHAT
    - Last msg is a drift warning + user says "okay I'll refocus" -> CHAT
    - Last msg is a drift warning + user says "actually I'm done with this" -> COMPLETE

    - "F002 is done" -> COMPLETE
    - "just pushed the changes" -> COMPLETE
    - "finished the login page" -> COMPLETE
    - "deployed to staging" -> COMPLETE
    - "ready for review" -> COMPLETE
    - "merged the PR" -> COMPLETE

    - "I'm lost, what do I do?" -> SUGGEST
    - "give me a task" -> SUGGEST

    - "I'm tired" -> CHAT
    - "this is hard" -> CHAT
    - "can you explain what F003 means?" -> CHAT
    - "how long will this take?" -> CHAT
    - "I want to change the tech stack" -> CHAT
    - "hello" AND no active feature AND no suggestion pending -> CHAT
    - Active feature exists + user says "okay I'm planning to set up the DB" -> CHAT
    - Active feature exists + user says "I'm going to install the libraries now" -> CHAT
    - Active feature exists + user says "let's start" (no prior work mentioned) -> START

    User Message: "{user_message}"

    Respond with exactly one word: SUGGEST, START, COMPLETE, or CHAT.
    """

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