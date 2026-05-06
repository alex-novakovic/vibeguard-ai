import json
import os
from data.schemas import VisionDoc
from data.state import ProjectState
from interfaces import StorageBackend
from datetime import datetime
from data.schemas import FeatureLogItem

class Storage(StorageBackend):

    def initialize_feature_log(self, vision_doc: VisionDoc) -> str:
        
        logs_dir = "data/logs" # save path to the log folder
        vision_path = os.path.join(logs_dir, "vision.json") # save path to the vision.json file
        feature_log_path = os.path.join(logs_dir, "feature_log.json") # save path to the feature_log.json file
        
        # creates logs directory if it doesn't exist
        os.makedirs(logs_dir, exist_ok=True)
        
        # writes vision.json to disk
        with open(vision_path, "w") as f:
            json.dump(vision_doc.model_dump(), f, indent=2)
        
        # creates an empty feature_log.json
        feature_log = {
            "features": {
                feature.id: {
                    "name": feature.name,
                    "status": "to_do",
                    "cycles": [],
                    "drift_events": []
                }
                for feature in vision_doc.backlog
            }
        }
        
        # writes feature_log.json to disk
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
                vision_doc = VisionDoc(**json.load(f)) # directly load and validate vision_doc from disk  
            
            # Load feature_log.json from disk into dict
            with open(feature_log_path, "r") as f:
                feature_log = json.load(f)
            
            # Populate ProjectState with existing data
            state = ProjectState(vision_doc, feature_log)
            
            return "existing", state
        
        # vision.json does not exist — signal Gradio to start scoping
        return "new", None

    def log_feature_cycle(self, feature_id: str, event: str, token_count: int = 0, alignment_note: str = None) -> dict:
        
        feature_log_path = "./data/logs/feature_log.json"

        if event not in ("start", "complete"):
            raise ValueError(f"Invalid event: {event}. Must be 'start' or 'complete'")
        
        # Read feature_log from disk
        with open(feature_log_path, "r") as f:
            raw = json.load(f)
        
        item = FeatureLogItem(**raw["features"][feature_id]) #reads the current feature log item from disk and validates it with pydantic
        # Get current timestamp
        now = datetime.now().isoformat()
        
        if event == "start":
            # Update status and record start time
            item.status = "in_progress"
            item.cycles.append({
                "started_at": now,
                "completed_at": None,
                "token_count": None,
                "alignment_note": None
            })
        
        elif event == "complete":
            # Update status and fill in the last cycle
            item.status = "complete"
            last_cycle = item.cycles[-1]
            last_cycle["completed_at"] = now
            last_cycle["token_count"] = token_count
            last_cycle["alignment_note"] = alignment_note
        
        raw["features"][feature_id] = item.model_dump()
        # Write updated feature_log back to disk
        with open(feature_log_path, "w") as f:
            json.dump(raw, f, indent=2)
        
        return item.model_dump()
