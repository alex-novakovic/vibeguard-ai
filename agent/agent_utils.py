COMPLETE_SIGNALS = [
    "done", "finished", "completed", "complete",
    "shipped", "deployed", "merged", "closed",
    "i finished", "i'm done", "it's done", "its done",
    "feature done", "feature complete", "feature finished",
    "wrapped up", "wrapped it up", "checked it off",
]

def detect_feature_complete(user_message: str) -> bool:
    """
    Detects whether the user is signaling that a feature is complete.
    Checks for common completion phrases in the user's message.
    """
    message_lower = user_message.lower().strip()
    return any(signal in message_lower for signal in COMPLETE_SIGNALS)

def calculate_remaining_minutes(vision_doc, feature_log) -> int:
    total_budget = vision_doc.availableTimeHours * 60
    spent = sum(
        sum(cycle.get("durationMinutes", 0) for cycle in feature.cycles)
        for feature in feature_log
    )
    return max(0, total_budget - spent)