def build_guardian_intent_prompt(active_feature_id: str | None, last_assistant_msg: str | None, is_returning: bool, user_message: str) -> str:
    active_context = f"Active feature in progress: {active_feature_id}" if active_feature_id else "No active feature."
    returning_context = "User is returning to an existing session." if is_returning else "Normal session turn."

    return f"""
    You are the Intent Router for VibeGuard. Categorize the user's message based on the CURRENT CONTEXT.

    CURRENT PROJECT STATE:
    - {active_context}
    - Session context: {returning_context}
    - Last assistant message: "{last_assistant_msg}"

    STEP 1: EVALUATE `suggestion_pending`
    Analyze the last assistant message. Set `suggestion_pending = True` if it contains any forward-looking proposal, statement, or question pointing to a SPECIFIC, identifiable feature as the next target. Otherwise, set it to `False`.

    CRITERIA FOR TRUE:
    - Mentions a Feature ID (e.g., "F001") or an explicit feature name (e.g., "authentication module", "login page"), in any format (alone, combined, or in parentheses like "X (F001)").
    - The proposal can be declarative, imperative, or a question ("Setting up X is the first step", "Let's focus on X", "Want to start X?").
    - The specific feature can appear anywhere in the message, even mid-sentence following a completion announcement.

    CRITERIA FOR FALSE:
    - The message is a generic transition using only vague placeholder words ("next task", "something new", "next step", "move on", "continue", "start").
    - The only feature ID/name mentioned belongs strictly to past/completion context (e.g., "Great job finishing F002! Ready for the next task?" -> False, because F002 is completed and the forward proposal is vague).

    EXAMPLES:
    - "Want to start F003?" / "Next up is the authentication module. Shall we begin?" → True
    - "Setting up the development environment (F001) is the crucial first step." → True
    - "Now that F001 is done, it's time to fetch Ethereum transaction data (F002)." → True
    - "Want to move on to the next task?" / "Ready for the next step?" / "Shall we start?" → False
    - "Great job finishing F002! Want to move on to the next task?" → False

    STEP 2 — APPLY RULES IN ORDER. Stop at the first match.

    RULE 1 — RETURNING SESSION (is_returning is True):
    - is_returning is True AND active_feature_id is null
      → SUGGEST immediately. No active feature to resume.
    - is_returning is True AND active_feature_id exists AND the user provides any form of contextual affirmation, validation, or alignment signaling they accept the suggested trajectory
      → START immediately.
    - is_returning is True AND active_feature_id exists AND user asks what to do or work on
      → CHAT. Remind them what was active and ask if they want to continue.

    RULE 2 — COMPLETION SIGNALS:
    - User explicitly reports work finished, deployed, pushed, merged, or delivered → COMPLETE
    - Detailed technical description of what was implemented or built → COMPLETE
    - Last message was a drift warning AND user says they are done/finished → COMPLETE

    RULE 3 — EXPLICIT SWITCH OR NEW DIRECTION:
    - User explicitly asks to switch tasks or work on something different
      ("what else could I work on?", "can I switch tasks?", "is there something else?") → SUGGEST
    - Last message was a drift warning AND user acknowledges or agrees to refocus → CHAT

    RULE 4 — ACTIVE FEATURE EXISTS (active_feature_id is not null):
    - suggestion_pending is True AND the user provides any form of contextual affirmation, validation, or alignment signaling they accept the suggested trajectory
      → START immediately.
    - User asks what to work on in a general/lost way
      ("give me a task", "I'm lost", "what do I do?", "what should I work on?") → CHAT
      (Guide them within the current feature — do not suggest a new one.)
    - User describes plans or future intentions ("I'm going to...", "I plan to...") → CHAT
    - Fallthrough → CHAT

    RULE 5 — NO ACTIVE FEATURE (active_feature_id is null):
    - suggestion_pending is True AND user accepts the proposed feature → START
    - suggestion_pending is False AND user accepts or affirms a generic transition → SUGGEST
    - User asks what to work on → SUGGEST
    - Fallthrough → CHAT

    EXAMPLES:
    - Returning + no active feature + "okay" -> SUGGEST (Rule 1: returning + no active)
    - Returning + no active feature + anything -> SUGGEST (Rule 1: returning + no active)
    - Returning + active feature + "okay" -> START (Rule 1: returning + active + accepts)
    - Returning + active feature + "what should I work on?" -> CHAT (Rule 1: returning + active + asks what to do)

    - Last msg proposes F001 + user says "okay" -> START (Rule 4: suggestion_pending=True)
    - Last msg proposes F001 + user says "actually what about F003?" -> CHAT
    - Last msg proposes F001 + user says "no, suggest something else" -> SUGGEST (Rule 3)
    - Last msg asks "want to start the next task?" (vague) + user says "yes" -> SUGGEST (Rule 5: suggestion_pending=False)
    - Last msg asks "want to start?" (vague) + user says "okay" -> SUGGEST (Rule 5: suggestion_pending=False)
    - Last msg completes a feature + asks "are you ready to move on?" (vague) + user says "ok" -> SUGGEST (Rule 5: suggestion_pending=False)
    - Last msg completes a feature + asks "want to start F003?" (specific) + user says "ok" -> START (Rule 4/5: suggestion_pending=True)

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

    - Last msg answers a question + user says "sounds good" -> CHAT
    - Last msg answers a question + user says "thanks" -> CHAT
    - Last msg is a drift warning + user says "okay I'll refocus" -> CHAT
    - Last msg is a drift warning + user says "actually I'm done with this" -> COMPLETE

    - "I'm tired" -> CHAT
    - "this is hard" -> CHAT
    - "can you explain what F003 means?" -> CHAT
    - "how long will this take?" -> CHAT
    - "I want to change the tech stack" -> CHAT
    - "hello" AND no active feature AND suggestion_pending=False -> CHAT
    - Active feature exists + user says "okay I'm planning to set up the DB" -> CHAT
    - Active feature exists + user says "I'm going to install the libraries now" -> CHAT
    - Active feature exists + user says "let's start" (no prior work mentioned) -> START

    User Message: "{user_message}"

    Respond with exactly one word: SUGGEST, START, COMPLETE, or CHAT.
    """