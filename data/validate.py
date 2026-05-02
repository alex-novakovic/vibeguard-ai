from data.schemas import (
    VISION_SCHEMA,
    BACKLOG_ITEM_SCHEMA,
    FEATURE_LOG_ITEM_SCHEMA,
    VALID_PRIORITIES,
    VALID_CONFIDENCE,
    VALID_STATUSES
)

def validate_vision_doc(vision_doc: dict) -> bool:
    
    # Check that all top-level fields exist and have the correct type
    for field, expected_type in VISION_SCHEMA.items():
        if field not in vision_doc:
            raise ValueError(f"Missing required field: {field}")
        if not isinstance(vision_doc[field], expected_type):
            raise ValueError(f"Field '{field}' has incorrect type. Expected {expected_type}, got {type(vision_doc[field])}")
    
    # Check that backlog is not empty
    if len(vision_doc["backlog"]) == 0:
        raise ValueError("Backlog must contain at least one item")
    
    # Check each backlog item against BACKLOG_ITEM_SCHEMA
    for item in vision_doc["backlog"]:
        
        # Check that all fields exist and have the correct type
        for field, expected_type in BACKLOG_ITEM_SCHEMA.items():
            if field not in item:
                raise ValueError(f"Backlog item missing required field: {field}")
            if not isinstance(item[field], expected_type):
                raise ValueError(f"Backlog item field '{field}' has incorrect type. Expected {expected_type}, got {type(item[field])}")
        
        # Backlog items must always be "to_do" — they are planned, never started
        if item["priority"] not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{item['priority']}'. Must be one of: {VALID_PRIORITIES}")
        if item["confidence"] not in VALID_CONFIDENCE:
            raise ValueError(f"Invalid confidence '{item['confidence']}'. Must be one of: {VALID_CONFIDENCE}")
        if item["status"] != "to_do":
            raise ValueError(f"Backlog item status must be 'to_do', got '{item['status']}'")
    
    return True