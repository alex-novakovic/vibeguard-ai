"""
Dev-only fake implementations — delete this file when Member A/B deliver real code.
Swap the imports in app.py to use the real backends.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from interfaces import AgentFunctions, StorageBackend


class FakeStorage(StorageBackend):

    def initialize_feature_log(self, vision_doc: dict) -> str:
        return "data/logs/feature_log.json"

    def load_or_create_project(self, state) -> str:
        return "existing" if (state is not None and state.vision_doc is not None) else "new"

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

    def __init__(self):
        vision_path = Path("data/logs/vision123.json")
        log_path = Path("data/logs/feature_log123.json")
        self.vision_doc = json.loads(vision_path.read_text()) if vision_path.exists() else None
        self.feature_log = json.loads(log_path.read_text()) if log_path.exists() else None
