from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Interface for Member B's storage layer (data/storage.py, data/state.py)."""

    @abstractmethod
    def initialize_feature_log(self, vision_doc: dict) -> str:
        """Create feature_log.json from vision_doc. Returns the file path."""
        ...

    @abstractmethod
    def load_or_create_project(self, state) -> tuple: #def load_or_create_project(self) -> tuple:
        """Check if vision.json exists. Returns 'existing' or 'new'."""
        ...

    @abstractmethod
    def log_feature_cycle(
        self,
        feature_id: str,
        event: str,
        token_count: int = 0,
        alignment_note: str = None,
    ) -> dict:
        """Record a start or complete event for a feature. Returns updated entry."""
        ...


class AgentFunctions(ABC):
    """Interface for Member A's standalone agent functions called directly from the UI."""

    @abstractmethod
    def suggest_next_task(self) -> dict:
        """Returns {"feature_id": str, "feature_name": str, "reason": str}."""
        ...

    @abstractmethod
    def monitor_for_drift(
        self,
        feature_id: str,
        user_description: str,
        time_spent_minutes: int,
        current_file: str,
    ) -> dict:
        """Returns {"is_drift": bool, "nudge_message": str}."""
        ...

    @abstractmethod
    def vision_alignment_check(self, feature_id: str, alignment_note: str) -> dict:
        """Returns {"is_aligned": bool, "feedback": str}."""
        ...
