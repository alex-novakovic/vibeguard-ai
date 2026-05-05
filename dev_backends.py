"""
Dev-only fake implementations — delete this file when Member A/B deliver real code.
Swap the imports in app.py to use the real backends.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import os
from data.schemas import VisionDoc

from interfaces import AgentFunctions, StorageBackend


class FakeStorage(StorageBackend):

    def initialize_feature_log(self, vision_doc: dict) -> str:
        return "data/logs/feature_log.json"

    def load_or_create_project(self) -> str:
        vision_path = "data/logs/vision.json"
        feature_log_path = "data/logs/feature_log.json"
        
        # Check if vision.json exists on startup
        if os.path.exists(vision_path) and os.path.exists(feature_log_path):
            
            # Load vision.json from disk into dict
            with open(vision_path, "r") as f:
              vision_doc = VisionDoc(**json.load(f)) #added to adjust to pydantic
            
            # Load feature_log.json from disk into dict
            with open(feature_log_path, "r") as f:
                feature_log = json.load(f)
            
            # Populate ProjectState with existing data
            state = DevProjectState(vision_doc, feature_log)
            
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
        return {
            "feature_id": feature_id,
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_count": token_count,
            "alignment_note": alignment_note,
        }


class FakeAgentFunctions(AgentFunctions):

    def suggest_next_task(self) -> dict:
        return {
            "feature_id": "feature_log",
            "feature_name": "Feature Log",
            "reason": "Core to your vision and still unstarted.",
        }

    def monitor_for_drift(
        self,
        feature_id: str,
        user_description: str,
        time_spent_minutes: int,
        current_file: str,
    ) -> dict:
        return {
            "is_drift": False,
            "nudge_message": f"You're {time_spent_minutes} min into `{feature_id}` — on track. Keep going!",
        }

    def vision_alignment_check(self, feature_id: str, alignment_note: str) -> dict:
        return {
            "is_aligned": True,
            "feedback": "This work aligns with your core product goal.",
        }


class DevProjectState:
    """
    Dev stand-in for data.state.ProjectState.
    Loads existing JSON files if present; sets fields to None otherwise.
    Replace with: from data.state import ProjectState
    """

    def __init__(self, vision_doc, feature_log):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
