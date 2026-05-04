import json
import uuid
from datetime import datetime, timezone
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import log_llm_call

PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"


class AgentSession:
    def __init__(self):
        self.session_id: str = str(uuid.uuid4())
        self.phase: str = PHASE_SCOPING
        self.scoping: ScopingSession = ScopingSession()
        self.project_state: ProjectState | None = None

    def _detect_scoping_complete(self, response: str) -> bool:
        last_line = response.strip().split("\n")[-1].strip().upper()
        return last_line == "SCOPING_COMPLETE"

    async def _finish_scoping(self):
        vision_doc = await self.scoping.scoping_session()

        self.phase = PHASE_GUARDIAN
        self.project_state = ProjectState(
            vision_doc=vision_doc,
            feature_log=[],
        )
        self.project_state.current_cycle_tokens = self.scoping.total_tokens

        log_llm_call(
            function_name="scoping_session",
            prompt="Full scoping conversation",
            response=json.dumps(vision_doc),
            tokens=self.scoping.total_tokens,
            session_id=self.session_id,
        )

    async def _handle_scoping_phase(self, user_message: str) -> str:
        response = await self.scoping.run_conversation_turn(user_message)
        
        # If we want to log each turn with tokens
        '''
        log_llm_call(
            function_name="run_conversation_turn",
            prompt=user_message,
            response=response,
            tokens=self.scoping.last_turn_tokens,
            session_id=self.session_id,
        )
        '''

        if self._detect_scoping_complete(response):
            await self._finish_scoping()
            clean_response = response.replace("SCOPING_COMPLETE", "").strip()
            return clean_response + "\n\n✅ Scoping complete! Your vision doc has been saved."

        return response

    async def _handle_guardian_phase(self, user_message: str) -> str:
        # TODO: wire in suggest_next_task() and monitor_for_drift()
        project_name = self.project_state.vision_doc.get("projectName", "your project")
        return f"[Guardian mode active] Working on: {project_name}. Guardian features coming soon."


async def run_agent(user_message: str, status: str, project_state: ProjectState, session: AgentSession) -> str:
    """
    Main entry point — same logic as before, now uses AgentSession.
    Member C calls this from Gradio.

    Args:
        user_message:  raw string from chat input
        status:        "new" or "existing" from load_or_create_project()
        project_state: existing ProjectState if status == "existing", else None
        session:       AgentSession instance from gr.State

    Returns:
        Agent response string to display in chat
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started."

    if status == "new":
        session.phase = PHASE_SCOPING
        return await session._handle_scoping_phase(user_message)

    elif status == "existing":
        session.phase = PHASE_GUARDIAN
        session.project_state = project_state
        return await session._handle_guardian_phase(user_message)

    else:
        return "Unknown agent phase. Please restart the session."