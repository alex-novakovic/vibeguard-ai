import json
import os
from data.validate import validate_vision_doc
from data.state import ProjectState
from datetime import datetime


def initialize_feature_log(vision_doc: dict) -> str:
    
    validate_vision_doc(vision_doc)
    
    # putanje
    logs_dir = "data/logs" # save path to the log folder
    vision_path = os.path.join(logs_dir, "vision.json") # save path to the vision.json file
    feature_log_path = os.path.join(logs_dir, "feature_log.json") # save path to the feature_log.json file
    
    # pravi data/logs/ folder ako ne postoji
    os.makedirs(logs_dir, exist_ok=True)
    
    # upisuje vision.json na disk
    with open(vision_path, "w") as f:
        json.dump(vision_doc, f, indent=2)
    
    # pravi prazan feature_log.json
    feature_log = {
        "features": {
            feature["id"]: {
                "name": feature["name"],
                "status": "to_do",
                "cycles": [],
                "drift_events": []
            }
            for feature in vision_doc["backlog"]
        }
    }
    
    # upisuje feature_log.json na disk
    with open(feature_log_path, "w") as f:
        json.dump(feature_log, f, indent=2)

    return feature_log_path  # ← kraj funkcije



def load_or_create_project() -> str:
    
    vision_path = "data/logs/vision.json"
    feature_log_path = "data/logs/feature_log.json"
    
    # Check if vision.json exists on startup
    if os.path.exists(vision_path) and os.path.exists(feature_log_path):
        
        # Load vision.json from disk into dict
        with open(vision_path, "r") as f:
            vision_doc = json.load(f)
        
        # Load feature_log.json from disk into dict
        with open(feature_log_path, "r") as f:
            feature_log = json.load(f)
        
        # Populate ProjectState with existing data
        state = ProjectState(vision_doc, feature_log)
        
        return "existing", state
    
    # vision.json does not exist — signal Gradio to start scoping
    return "new", None

def log_feature_cycle(feature_id: str, event: str, token_count: int = 0, alignment_note: str = None) -> dict:
    
    feature_log_path = "./data/logs/feature_log.json"
    
    # Read feature_log from disk
    with open(feature_log_path, "r") as f:
        feature_log = json.load(f)
    
    # Get current timestamp
    now = datetime.now().isoformat()
    
    if event == "start":
        # Update status and record start time
        feature_log["features"][feature_id]["status"] = "in_progress"
        feature_log["features"][feature_id]["cycles"].append({
            "started_at": now,
            "completed_at": None,
            "token_count": None,
            "alignment_note": None
        })
    
    elif event == "complete":
        # Update status and fill in the last cycle
        feature_log["features"][feature_id]["status"] = "complete"
        last_cycle = feature_log["features"][feature_id]["cycles"][-1]
        last_cycle["completed_at"] = now
        last_cycle["token_count"] = token_count
        last_cycle["alignment_note"] = alignment_note

    if event not in ("start", "complete"):
     raise ValueError(f"Invalid event: {event}. Must be 'start' or 'complete'")    
    
    # Write updated feature_log back to disk
    with open(feature_log_path, "w") as f:
        json.dump(feature_log, f, indent=2)
    
    return feature_log["features"][feature_id]