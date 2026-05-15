from agent.scoping import ScopingSession
from data.state import ProjectState
from typing import List, Dict
from data.logger import Logger

PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"


class AgentSession:
    """
    Holds per-user state that persists between graph runs.
    The graph itself is stateless — AgentSession carries state across turns.
    """
    def __init__(self):
        self.user_id: str = str()
        self.phase: str = PHASE_SCOPING
        self.scoping: ScopingSession | None = ScopingSession()
        self.project_state: ProjectState = ProjectState()
        self.just_completed_scoping: bool = False
        self.messages: List[Dict] = []  # This will hold the conversation history
        self.alignment_note: str | None = None
        self.drift_note: str | None = None
        self.logger: Logger = Logger()
        self.is_returning: bool = False



