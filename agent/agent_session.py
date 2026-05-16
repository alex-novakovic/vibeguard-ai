from agent.scoping import ScopingSession
from data.state import ProjectState
from typing import List, Dict, TypedDict, Literal
from data.logger import Logger


PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"

# ── 1. STATE ─────────────────────────────────────────────────────────────────
# This is what flows through the graph — replaces agent_state dict
class AgentState(TypedDict):
    user_id: str
    phase: str
    user_message: str
    messages: List[Dict[str, str]]
    response: str
    scoping: ScopingSession | None
    project_state: ProjectState | None
    logger: Logger | None
    just_completed_scoping: bool
    is_returning: bool
    alignment_note: str | None
    completion_status: Literal["IDLE", "COLLECTING"]  
    completion_context: Dict[str, any]  # Stores collected data temporarily

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
        self.completion_status: str = "IDLE"
        self.completion_context: dict = {"collected_info": [], "attempts": 0}



