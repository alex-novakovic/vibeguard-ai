# replace the PRIORITY OVERRIDE block with this:
def build_guardian_intent_prompt(active_feature_id: str | None, last_assistant_msg: str | None, is_returning: bool, user_message: str) -> str:
    active_context = f"Active feature in progress: {active_feature_id}" if active_feature_id else "No active feature."
    
    override_rule = """
    ⚠️ PRIORITY OVERRIDE — RETURNING SESSION:
        The user just returned to an existing session with an active feature.
        Their first message is almost certainly just an acknowledgment.
        Return START immediately, no further analysis needed.
        This rule overrides ALL other rules below.
    """ if is_returning else ""

    return f"""
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
    - Do NOT use START if the assistant is asking whether the user wants a task without proposing a specific one — an affirmative reply there is SUGGEST.
    2. SUGGEST: User explicitly asks for a new task or direction ("what's next?", "give me something to do").
    3. COMPLETE: User confirms work is done ("finished", "done", "pushed", "deployed", "ready for review").
    4. CHAT: Everything else — questions, acknowledgments when nothing was proposed, technical help.

    EXAMPLES:
    - Last msg proposes F001 + user says "okay" -> START
    - Last msg proposes F001 + user says "actually what about F003?" -> CHAT
    - Last msg proposes F001 + user says "no, suggest something else" -> SUGGEST
    - Last msg asks if user wants a next task (no specific feature proposed) + user says "yes" -> SUGGEST

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