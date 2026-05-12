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


    def _detect_scoping_complete(self, response: str) -> bool:
        last_line = response.strip().split("\n")[-1].strip().upper()
        return last_line == "SCOPING_COMPLETE"

    async def _finish_scoping(self):
        vision_doc = await self.scoping.scoping_session()

        self.phase = PHASE_GUARDIAN
        self.project_state.vision_doc = vision_doc
        self.project_state.current_cycle_tokens = self.scoping.total_tokens

        self.logger.log_llm_call(
            function_name="scoping_session",
            prompt="Full scoping conversation",

            response=json.dumps(vision_doc.model_dump()),  #adjusted to pydantic

            tokens=self.scoping.total_tokens,
            user_id=self.user_id,
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
            user_id=self.user_id,
        )
        '''

        if self._detect_scoping_complete(response):
            await self._finish_scoping()
            clean_response = response.replace("SCOPING_COMPLETE", "").strip()
            return clean_response + "\n\n✅ Scoping complete! Your vision doc has been saved."

        return response

    async def _handle_guardian_phase(self, user_message: str) -> str:
        # TODO: wire in suggest_next_task() and monitor_for_drift()
        project_name = self.project_state.vision_doc.projectName #adjusted to pydantic
        return f"[Guardian mode active] Working on: {project_name}. Guardian features coming soon."

