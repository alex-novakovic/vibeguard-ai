import json
import os
from datetime import datetime, timezone
from pydantic import ValidationError
from data.schemas import VisionDoc, FeatureLogItem
from data.state import ProjectState
from interfaces import StorageBackend
import uuid
from data.schemas import SessionLog, SessionEntry

from utils.exceptions import (
    FileSystemError,
    ParsingFailed,
    EventError,
    MissingFeatureId,
    MissingSessionId
)

class Storage(StorageBackend):

    def initialize_feature_log(self, vision_doc: VisionDoc) -> str:

        logs_dir = "data/logs"
        vision_path = os.path.join(logs_dir, "vision.json")
        feature_log_path = os.path.join(logs_dir, "feature_log.json")

        try:
            os.makedirs(logs_dir, exist_ok=True)

            with open(vision_path, "w") as f:
                json.dump(vision_doc.model_dump(), f, indent=2)

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

            with open(feature_log_path, "w") as f:
                json.dump(feature_log, f, indent=2)

        except OSError as e:
            raise FileSystemError(f"Failed to write project files to {logs_dir}: {e}") from e

        return feature_log_path 

    def load_or_create_project(self) -> tuple:   
            
        vision_path = "data/logs/vision.json"
        feature_log_path = "data/logs/feature_log.json"
        
        if os.path.exists(vision_path) and os.path.exists(feature_log_path):
            try:
                with open(vision_path, "r") as f:
                    vision_doc = VisionDoc(**json.load(f))

                with open(feature_log_path, "r") as f:
                    feature_log = json.load(f)

                state = ProjectState(vision_doc, feature_log)
                return "existing", state

            except (json.JSONDecodeError, ValidationError) as e:
                raise ParsingFailed(f"Project files are corrupted and could not be loaded: {e}") from e
            except OSError as e:
                raise FileSystemError(f"Failed to read project files: {e}") from e

        return "new", None

    def log_feature_cycle(self, feature_id: str, event: str, token_count: int = 0, alignment_note: str = None) -> dict:
        
        feature_log_path = "./data/logs/feature_log.json"

        if event not in ("start", "complete"):
            raise EventError(f"Invalid event: {event}. Must be 'start' or 'complete'")

        try:
            with open(feature_log_path, "r") as f:
                raw = json.load(f)
        except FileNotFoundError:
            raise FileSystemError("Feature log not found. Call initialize_feature_log first.")
        except json.JSONDecodeError as e:
            raise ParsingFailed(f"Feature log file is corrupted: {e}") from e

        if feature_id not in raw.get("features", {}):
            raise MissingFeatureId(f"Feature '{feature_id}' not found in feature log.")

        try:
            item = FeatureLogItem(**raw["features"][feature_id])
        except ValidationError as e:
            raise ParsingFailed(f"Feature log entry for '{feature_id}' is invalid: {e}") from e

        now = datetime.now(timezone.utc).isoformat()

        if event == "start":
            item.status = "in_progress"
            item.cycles.append({
                "started_at": now,
                "completed_at": None,
                "token_count": None,
                "alignment_note": None
            })

        elif event == "complete":
            if not item.cycles:
                raise EventError(f"Cannot complete '{feature_id}': no active cycle. Call log_feature_cycle with event='start' first.")
            item.status = "complete"
            last_cycle = item.cycles[-1]
            last_cycle["completed_at"] = now
            last_cycle["token_count"] = token_count
            last_cycle["alignment_note"] = alignment_note

        raw["features"][feature_id] = item.model_dump()

        try:
            with open(feature_log_path, "w") as f:
                json.dump(raw, f, indent=2)
        except OSError as e:
            raise FileSystemError(f"Failed to write feature log: {e}") from e

        return item.model_dump()
    
    def start_session(self) -> dict:
        
        session_log_path = "./data/logs/session_log.json"
        os.makedirs("./data/logs", exist_ok=True)
        
        # Load existing session_log or create a new one
        if os.path.exists(session_log_path):
            with open(session_log_path, "r") as f:
                data = json.load(f)
            session_log = SessionLog(**data)
        else:
            session_log = SessionLog()
        
        # Create new session entry
        new_session = SessionEntry(
            workSessionId=str(uuid.uuid4()),
            startTime=datetime.now().isoformat()
        )
        
        session_log.sessions.append(new_session)
        
        try:
          with open(session_log_path, "w") as f:
            json.dump(session_log.model_dump(), f, indent=2)
        except OSError as e:
           raise FileSystemError(f"Failed to write session log: {e}") from e

        return new_session.model_dump()


    def end_session(self, session_id: str, total_tokens: int) -> dict:
        
        session_log_path = "./data/logs/session_log.json"
        feature_log_path = "./data/logs/feature_log.json"
        
        # Load session_log
        try:
            with open(session_log_path, "r") as f:
              session_log = SessionLog(**json.load(f))
        except FileNotFoundError:
            raise FileSystemError("Session log not found. Call start_session first.")
        except json.JSONDecodeError as e:
            raise ParsingFailed(f"Session log file is corrupted: {e}") from e

        # Load feature_log
        try:
            with open(feature_log_path, "r") as f:
                feature_log = json.load(f)
        except FileNotFoundError:
            raise FileSystemError("Feature log not found. Call initialize_feature_log first.")
        except json.JSONDecodeError as e:
            raise ParsingFailed(f"Feature log file is corrupted: {e}") from e
        
         
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
        ] #going through all features and checking which ones are marked as complete
        
        drift_count = sum(
            len(fdata["drift_events"])
            for fdata in features.values()
        )#going through all features and summing up the number of drift events across all features
        
        # Calculate session duration
        start = datetime.fromisoformat(session.startTime)
        end = datetime.now()
        duration = int((end - start).total_seconds() / 60)
        
        # Update session
        session.endTime = end.isoformat()
        session.featureCyclesCompleted = completed
        session.driftEventsCount = drift_count
        session.totalTokensUsed = total_tokens
        session.totalDurationMinutes = duration
        
        with open(session_log_path, "w") as f:
            json.dump(session_log.model_dump(), f, indent=2)
        
        return session.model_dump()