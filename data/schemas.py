VISION_SCHEMA = {
    "projectName": str,
    "visionStatement": str,
    "targetUser": str,
    "problemStatement": str,
    "availableTime": (str, type(None)),
    "availableTimeHours": int,
    "experienceLevel": (str, type(None)),
    "successCriteria": str,
    "constraints": (str, type(None)),
    "techStack": list,
    "externalDependencies": list,
    "niceToHave": list,
    "backlog": list
}

BACKLOG_ITEM_SCHEMA = {
    "id": str,
    "name": str,
    "description": str,
    "priority": str,
    "status": str,
    "estimatedMinutes": int,
    "dependencies": list,
    "confidence": str,
    "scopeFlag": bool,
    "scopeFlagReason": (str, type(None))
}

FEATURE_LOG_ITEM_SCHEMA = {
    "name": str,
    "status": str,
    "cycles": list,
    "drift_events": list
}

VALID_PRIORITIES = {"critical", "high", "medium", "low"}
VALID_CONFIDENCE = {"high", "low"}
VALID_STATUSES = {"to_do", "in_progress", "complete"}