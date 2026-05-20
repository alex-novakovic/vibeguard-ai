# replace the PRIORITY OVERRIDE block with this:
def build_guardian_intent_prompt(active_feature_id: str | None, last_assistant_msg: str | None, is_returning: bool, user_message: str) -> str:
    active_context = f"Active feature in progress: {active_feature_id}" if active_feature_id else "No active feature."
    returning_context = "User is returning to an existing session." if is_returning else "Normal session turn."

    return f"""
    You are the Intent Router for VibeGuard. Categorize the user's message based on the CURRENT CONTEXT.

    CURRENT PROJECT STATE:
    - {active_context}
    - Session context: {returning_context}
    - Last assistant message: "{last_assistant_msg}"

    HARD RULE: If active_feature_id is not null:
    - is_returning is True AND user asks what to do or work on
      → CHAT. Remind them what was active and ask if they want to continue.
    - is_returning is True AND user explicitly accepts or acknowledges
      ("okay", "yes", "sure", "let's go") → START immediately.
    - is_returning is False AND user asks what to work on in a
      general/lost way ("give me a task", "I'm lost", "what do I do?",
      "what should I work on?") → CHAT.
      Guide them within the current feature, do not suggest a new one.
    - User explicitly asks to work on something ELSE or different
      ("what else could I work on?", "can I switch tasks?",
      "is there something else I can do?") → SUGGEST
    - User explicitly acknowledges or accepts after a suggestion
      ("okay", "let's go", "sure") → START
    Only use SUGGEST when active_feature_id is null OR user explicitly
    wants to switch away from the current feature.

    If active_feature_id is null:
    - is_returning is True → SUGGEST immediately.
      No active feature to resume, pick something from the backlog.
    - User asks what to work on → SUGGEST.

    TASK:
    Read the last assistant message carefully. Determine:
    1. Was the assistant proposing a specific, actionable task — whether by feature ID, feature name, OR a clear unambiguous task description? (suggestion_pending = True)
    - "Want to start F003?" → True
    - "I suggest F002 — Fetch Transaction Data. Ready?" → True
    - "Are you ready to move on to the next item?" → False (no specific feature named)
    - "Shall we continue?" → False
    - "Ready for the next step?" → False

    Then classify the user's reply using these rules:

    CATEGORIES & STRICT RULES:
    1. START: Use this when the user is committing to begin a feature they haven't started yet. This includes:
    - suggestion_pending is True AND user accepts (e.g., "okay", "let's go", "do it", "sure")
    - Active feature exists AND user says they are about to start ("I'll start now", "beginning now", "on it")
    - Do NOT use START if the user is describing work already in progress, asking questions, or reporting plans — that is CHAT.
    - Do NOT use START if the assistant is asking whether the user wants a task without proposing a specific one — an affirmative reply there is SUGGEST.
    2. SUGGEST: User explicitly asks for a new task or direction ("what's next?", "give me something to do").
    3. COMPLETE: User confirms work is done ("finished", "done", "pushed", "deployed", "ready for review").
    - Detailed work reports describing what was implemented, built, or delivered — even if they don't use the word "done"
    4. CHAT: Everything else — questions, acknowledgments when nothing was proposed, technical help.


    EXAMPLES:
    - Last msg proposes F001 + user says "okay" -> START
    - Last msg proposes F001 + user says "actually what about F003?" -> CHAT
    - Last msg proposes F001 + user says "no, suggest something else" -> SUGGEST
    - Last msg asks if user wants a next task (no specific feature proposed) + user says "yes" -> SUGGEST
    - Last msg completes a feature and asks "are you ready to move on?" (no specific feature named) + user says "ok" -> SUGGEST
    - Last msg completes a feature and asks "want to start F003?" (specific feature named) + user says "ok" -> START

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

    - "I'm lost, what do I do?" AND no active feature -> SUGGEST
    - "I'm lost, what do I do?" AND active feature exists -> CHAT
    - "give me a task" AND no active feature -> SUGGEST
    - "give me a task" AND active feature exists -> CHAT

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