import json
import os
from data.validate import validate_vision_doc


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
