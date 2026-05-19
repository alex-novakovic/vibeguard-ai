from __future__ import annotations
from typing import TYPE_CHECKING

from data.schemas import SessionEntry
if TYPE_CHECKING:
    from agent.agent_session import AgentSession
    from data.schemas import VisionDoc
    from typing import List, Optional
    from data.schemas import FeatureLogItem, SessionEntry 
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    """Interface for Member B's storage layer (data/storage.py, data/state.py)."""

    @abstractmethod
    async def initialize_feature_log(self, vision_doc: VisionDoc) -> list:
        """Create feature_log.json from vision_doc. Returns feature_log."""
        ...

    @abstractmethod
    async def load_or_create_project(self, user_id: str) -> tuple:
        """Check if vision.json exists. Returns ('existing', state) or ('new', state)."""
        ...

    @abstractmethod
    async def log_feature_cycle(
        self,
        feature_log: dict,
        feature_id: str,
        event: str,
        alignment_note: str = None,
        drift_event: str = None
    ) -> list:
        """Record a start or complete event for a feature. Returns updated feature_log."""
        ...

    @abstractmethod
    async def start_session(self, user_id: str) -> SessionEntry:
        """Record start session. Return session_log"""
        ...

    @abstractmethod
    async def end_session(self, user_id: str, session_id: str, total_tokens: int) -> SessionEntry:
        """Record end session. Return session_log"""
        ...

    @abstractmethod
    async def dump_logs(self, vision_doc: Optional[VisionDoc], feature_log: List[FeatureLogItem], session_log: List[SessionEntry]) -> None:
        """Save/Update vision document, feature logs, and session entries in MongoDB."""
        ...

class LoggerBackend(ABC):
    """Interface for Member B's logging layer (data/logger.py)."""

    @abstractmethod
    async def log_llm_call(
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
