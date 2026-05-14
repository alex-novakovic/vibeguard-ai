import json
import os
from datetime import datetime
from utils.common import now, now_dt
from pydantic import ValidationError
from data.schemas import VisionDoc, FeatureLogItem, SessionLog, SessionEntry
from data.state import ProjectState
from interfaces import StorageBackend
import uuid

from utils.exceptions import (
    FileSystemError,
    ParsingFailed,
    EventError,
    MissingFeatureId,
    MissingSessionId
)

class Storage(StorageBackend):

    def initialize_feature_log(self, vision_doc: VisionDoc) -> dict:
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

        return feature_log 

    def load_or_create_project(self, user_id: str) -> tuple:   
            
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        vision_path      = os.path.join(BASE_DIR, "logs", "vision_doc.json")
        feature_log_path = os.path.join(BASE_DIR, "logs", "feature_log.json")
        session_log_path = os.path.join(BASE_DIR, "logs", "session_log.json")
        
        if os.path.exists(vision_path) and os.path.exists(feature_log_path) and os.path.exists(session_log_path):
            try:
                with open(vision_path, "r") as f:
                    vision_doc = VisionDoc(**json.load(f))

                with open(feature_log_path, "r") as f:
                    feature_log = json.load(f)

                with open(session_log_path, "r") as f:
                    session_log = SessionLog(**json.load(f))

                state = ProjectState(vision_doc, feature_log, session_log)
                return "existing", state

            except (json.JSONDecodeError, ValidationError) as e:
                raise ParsingFailed(f"Project files are corrupted and could not be loaded: {e}") from e
            except OSError as e:
                raise FileSystemError(f"Failed to read project files: {e}") from e

        return "new", ProjectState()

    def log_feature_cycle(self, feature_log: dict, feature_id: str, event: str, alignment_note: str = None, drift_event: str = None) -> dict:
        
        if event not in ("start", "complete"):
            raise EventError(f"Invalid event: {event}. Must be 'start' or 'complete'")

        if feature_id not in feature_log.get("features", {}):
            raise MissingFeatureId(f"Feature '{feature_id}' not found in feature log.")

        try:
            item = FeatureLogItem(**feature_log["features"][feature_id])
        except ValidationError as e:
            raise ParsingFailed(f"Feature log entry for '{feature_id}' is invalid: {e}") from e

        now = now()

        if event == "start":
            item.status = "in_progress"
            item.cycles.append({
                "started_at": now,
                "completed_at": None,
                "alignment_note": None
            })
            item.drift_events.append({
                "drift_time": now,
                "drift_note": drift_event
            })

        elif event == "complete":
            if not item.cycles:
                raise EventError(f"Cannot complete '{feature_id}': no active cycle. Call log_feature_cycle with event='start' first.")
            item.status = "complete"
            last_cycle = item.cycles[-1]
            last_cycle["completed_at"] = now
            last_cycle["alignment_note"] = alignment_note

        feature_log["features"][feature_id] = item.model_dump()

        return feature_log
    
    def start_session(self, session_log: SessionLog) -> SessionLog:
        
        # Create new session entry
        new_session = SessionEntry(
            workSessionId=str(uuid.uuid4()),
            startTime=now()
        )
        
        session_log.sessions.append(new_session)
        
        return session_log

    def end_session(self, session_id: str, session_log: SessionLog, feature_log: dict, total_tokens: int) -> SessionLog:
        
        # Find session by session_id
        session = next(
            (s for s in session_log.sessions if s.workSessionId == session_id),
            None
        )
        
        if session is None:
            raise MissingSessionId(f"Session {session_id} not found")
        
        # Aggregate feature_log
        features = feature_log["features"]
        
        completed = [
            fid for fid, fdata in features.items()
            if fdata["status"] == "complete"
        ] # going through all features and checking which ones are marked as complete
        
        drift_count = sum(
            len(fdata["drift_events"])
            for fdata in features.values()
        ) # going through all features and summing up the number of drift events across all features
        
        # Calculate session duration
        start = datetime.fromisoformat(session.startTime)
        end = now_dt()
        duration = int((end - start).total_seconds() / 60)
        
        # Update session
        session.endTime = end.isoformat()
        session.featureCyclesCompleted = completed
        session.driftEventsCount = drift_count
        session.totalTokensUsed = total_tokens
        session.totalDurationMinutes = duration
        
        return session_log
    
    def dump_logs(self, vision_doc: VisionDoc, feature_log: dict, session_log: SessionLog) -> None:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        log_dir_path = os.path.join(BASE_DIR, "logs")

        try:
            os.makedirs(log_dir_path, exist_ok=True)
        except OSError as e:
            raise FileSystemError(f"Failed to create log directory {log_dir_path}: {e}") from e

        if vision_doc is not None:
            vision_doc_path = os.path.join(log_dir_path, "vision_doc.json")
            try:
                with open(vision_doc_path, "w") as f:
                    json.dump(vision_doc.model_dump(), f, indent=2)
            except OSError as e:
                raise FileSystemError(f"Failed to write vision doc: {e}") from e

        if feature_log is not None:
            feature_log_path = os.path.join(log_dir_path, "feature_log.json")
            try:
                with open(feature_log_path, "w") as f:
                    json.dump(feature_log, f, indent=2)
            except OSError as e:
                raise FileSystemError(f"Failed to write feature log: {e}") from e

        if session_log is not None:
            session_log_path = os.path.join(log_dir_path, "session_log.json")
            try:
                with open(session_log_path, "w") as f:
                    json.dump(session_log.model_dump(), f, indent=2)
            except OSError as e:
                raise FileSystemError(f"Failed to write session log: {e}") from e
