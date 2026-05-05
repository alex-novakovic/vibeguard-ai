import json
import os
from data.validate import validate_vision_doc
from data.state import ProjectState
from interfaces import StorageBackend
from datetime import datetime

class Storage(StorageBackend):

    def initialize_feature_log(self, vision_doc: dict) -> str:
        validate_vision_doc(vision_doc)
    
        logs_dir = "data/logs" # saves path to the log folder
        vision_path = os.path.join(logs_dir, "vision.json") # saves path to the vision.json file
        feature_log_path = os.path.join(logs_dir, "feature_log.json") # saves path to the feature_log.json file
        
        # creates data/logs/ folder if it doesn't exist
        os.makedirs(logs_dir, exist_ok=True)
        
        # writes vision.json on disk
        with open(vision_path, "w") as f:
            json.dump(vision_doc, f, indent=2)
        
        # creates an empty feature_log.json
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
        
        # writes feature_log.json on disk
        with open(feature_log_path, "w") as f:
            json.dump(feature_log, f, indent=2)

        return feature_log_path 

    def load_or_create_project(self) -> tuple:   
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

    def log_feature_cycle(
        self,
        feature_id: str,
        event: str,
        token_count: int = 0,
        alignment_note: str = None,
    ) -> dict:
        feature_log_path = "./data/logs/feature_log.json"

        if event not in ("start", "complete"):
            raise ValueError(f"Invalid event: {event}. Must be 'start' or 'complete'") 
        
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

        # Write updated feature_log back to disk
        with open(feature_log_path, "w") as f:
            json.dump(feature_log, f, indent=2)
        
        return feature_log["features"][feature_id]
