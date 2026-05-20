from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent.agent_session import AgentSession
    from data.schemas import VisionDoc, SessionLog
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    """Interface for Member B's storage layer (data/storage.py, data/state.py)."""

    @abstractmethod
    def initialize_feature_log(self, vision_doc: VisionDoc) -> dict:
        """Create feature_log.json from vision_doc. Returns feature_log."""
        ...

    @abstractmethod
    def load_or_create_project(self, user_id: str) -> tuple:
        """Check if vision.json exists. Returns ('existing', state) or ('new', state)."""
        ...

    @abstractmethod
    def log_feature_cycle(
        self,
        feature_log: dict,
        feature_id: str,
        event: str,
        vision_doc: VisionDoc,
        alignment_note: str = None,
        drift_event: str = None
    ) -> dict:
        """Record a start or complete event for a feature. Returns updated feature_log."""
        ...

    @abstractmethod
    def start_session(self, session_log: SessionLog) -> tuple:
        """Record start session. Return session ID and session_log"""
        ...

    @abstractmethod
    def end_session(self, session_id: str, session_log: SessionLog, feature_log: dict, total_tokens: int) -> SessionLog:
        """Record end session. Return session_log"""
        ...

    @abstractmethod
    def dump_logs(self, vision_doc: VisionDoc, feature_log: dict, session_log: SessionLog) -> None:
        """Writes all log files."""
        ...

class LoggerBackend(ABC):
    """Interface for Member B's logging layer (data/logger.py)."""

    @abstractmethod
    def log_llm_call(
        self,
        function_name: str,
        prompt: str,
        response: str,
        tokens: int,
        session_id: str,
    ) -> None:
        """Append an LLM call record to the log file."""
        ...


class AgentFunctions(ABC):
    """Interface for Member A's standalone agent functions called directly from the UI."""

    @abstractmethod
    async def run_agent(self, user_message: str, status: str, session: AgentSession) -> tuple:
        """Perform agent run."""
        ...
