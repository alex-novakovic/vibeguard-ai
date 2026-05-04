import json
import os
from data.validate import validate_vision_doc
from data.state import ProjectState
from interfaces import StorageBackend




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


class Storage(StorageBackend):

    def initialize_feature_log(self, vision_doc: dict) -> str:
        return initialize_feature_log(vision_doc)

    def load_or_create_project(self) -> tuple:
        return load_or_create_project()

    def log_feature_cycle(
        self,
        _feature_id: str,
        _event: str,
        _token_count: int = 0,
        _alignment_note: str = None,
    ) -> dict:
        raise NotImplementedError("log_feature_cycle is pending PR merge")
