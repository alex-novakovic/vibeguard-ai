from agent.scoping import ScopingSession
from data.state import ProjectState
from typing import List, Dict

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
        self.scoping: ScopingSession = ScopingSession()
        self.project_state: ProjectState = ProjectState()
        self.just_completed_scoping: bool = False
        self.messages: List[Dict] = []  # This will hold the conversation history



