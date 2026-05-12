from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import Logger
from data.storage import Storage
import json
import uuid

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
        self.logger: Logger = Logger()



