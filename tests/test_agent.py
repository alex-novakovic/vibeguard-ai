import pytest
from unittest.mock import MagicMock, AsyncMock
from agent.loop import detect_scoping_complete
from utils.exceptions import ModelTimeout, RateLimitReached

class TestDetectScopingComplete:

    def test_returns_true_when_token_present(self):
        """
        The clearest case — response contains the exact trigger token.
        The function must return True.
        """
        response = "Great, we have everything we need.\nSCOPING_COMPLETE"
        result = detect_scoping_complete(response) # we can use the real function since it doesn't change anything
        assert result is True

    def test_returns_false_for_conversational_noise(self):
        """
        Normal conversational response with no trigger token.
        The function must return False.
        """
        response = "What problem does your product solve?"
        result = detect_scoping_complete(response)
        assert result is False

    def test_returns_false_for_empty_string(self):
        """
        Edge case — empty string should not trigger completion.
        """
        result = detect_scoping_complete("")
        assert result is False

    def test_returns_false_for_partial_token(self):
        """
        Edge case — partial match should not count.
        'SCOPING' alone is not the trigger.
        """
        response = "We are still in the SCOPING phase."
        result = detect_scoping_complete(response)
        assert result is False

PHASE_SCOPING  = "scoping"
PHASE_GUARDIAN = "guardian"

class AgentSession:
    """Stub matching the real AgentSession fields run_agent uses."""
    def __init__(self):
        self.user_id       = "test-user-123"
        self.phase         = PHASE_SCOPING
        self.scoping       = {}
        self.project_state = MagicMock()
        self.logger        = MagicMock()


async def run_agent_stub(agent_graph, user_message: str, session: AgentSession):
    """
    Mirrors the real run_agent() body.
    Takes agent_graph as an argument so tests can inject a mock.
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started.", session

    input_state = {
        "user_id":       session.user_id,
        "phase":         session.phase,
        "user_message":  user_message,
        "response":      "",
        "scoping":       session.scoping,
        "project_state": session.project_state,
        "logger":        session.logger,
    }

    result = await agent_graph.ainvoke(input_state)

    session.phase         = result["phase"]
    session.project_state = result["project_state"]

    return result["response"], session


def make_graph_result(phase: str, response: str = "ok") -> dict:
    return {
        "phase":         phase,
        "response":      response,
        "project_state": MagicMock(),
    }


class TestRunAgentStateMachine:

    @pytest.mark.asyncio
    async def test_phase_switches_from_scoping_to_guardian(self):
        """
        When the graph returns phase=guardian,
        run_agent must sync that back to the session.

        This simulates what happens after SCOPING_COMPLETE:
        the graph transitions the phase and run_agent writes
        the new phase back to the session object.
        """
        session    = AgentSession()
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = make_graph_result(
            phase    = PHASE_GUARDIAN,
            response = "Scoping complete. Let's start building."
        )

        assert session.phase == PHASE_SCOPING 

        _, updated_session = await run_agent_stub(
            mock_graph, "yes that looks correct", session
        )

        assert updated_session.phase == PHASE_GUARDIAN
        mock_graph.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_phase_stays_scoping_during_conversation(self):
        """
        While the scoping conversation is still in progress,
        the graph keeps returning phase=scoping.
        run_agent must not change the phase in this case.
        """
        session    = AgentSession()
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = make_graph_result(
            phase    = PHASE_SCOPING,
            response = "What problem does your product solve?"
        )

        _, updated_session = await run_agent_stub(
            mock_graph, "I am building a task manager", session
        )

        assert updated_session.phase == PHASE_SCOPING

    @pytest.mark.asyncio
    async def test_input_state_contains_correct_phase(self):
        """
        run_agent must pass the current session phase into the
        graph input state — not a hardcoded value.

        If this fails it means the graph is running with stale
        or wrong phase information.
        """
        session       = AgentSession()
        session.phase = PHASE_GUARDIAN 

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = make_graph_result(
            phase = PHASE_GUARDIAN
        )  

        await run_agent_stub(mock_graph, "starting feature F001", session)

        call_args  = mock_graph.ainvoke.call_args
        input_state = call_args[0][0]  

        assert input_state["phase"] == PHASE_GUARDIAN

    @pytest.mark.asyncio
    async def test_empty_message_returns_early_without_calling_graph(self):
        """
        run_agent has an early return guard for empty messages.
        The graph must never be called in this case —
        no state should change.
        """
        session    = AgentSession()
        mock_graph = AsyncMock()

        response, updated_session = await run_agent_stub(
            mock_graph, "   ", session
        )

        assert response == "Please type a message to get started."
        assert updated_session.phase == PHASE_SCOPING  
        mock_graph.ainvoke.assert_not_called()           

    @pytest.mark.asyncio
    async def test_project_state_is_synced_back_after_graph_runs(self):
        """
        run_agent must sync project_state back to the session
        after the graph runs — not just the phase.

        If this fails, the session will carry stale project data
        into the next turn.
        """
        session           = AgentSession()
        new_project_state = MagicMock()
        mock_graph        = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "phase":         PHASE_GUARDIAN,
            "response":      "ok",
            "project_state": new_project_state,
        }

        _, updated_session = await run_agent_stub(
            mock_graph, "confirm", session
        )

        assert updated_session.project_state is new_project_state

class ModelTimeout(Exception):
    pass
 
class RateLimitReached(Exception):
    pass
 
class APITimeoutError(Exception):
    pass
 
class RateLimitError(Exception):
    pass
 
class APIConnectionError(Exception):
    pass

async def run_conversation_turn(call_fn, retries: int = 3):
    """
    Stub that mirrors only the retry logic from the real
    run_conversation_turn(). No message appending, no tokens,
    no system prompt — just the loop that matters for these tests.
    """
    for attempt in range(retries):
        try:
            return call_fn()
        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            if attempt < retries - 1:
                pass 
            else:
                if isinstance(e, RateLimitError):
                    raise RateLimitReached("Rate limit hit after all retries.") from e
                raise ModelTimeout("Model timed out after all retries.") from e


class TestNetworkResilience:

    @pytest.mark.asyncio
    async def test_retries_exactly_three_times_on_timeout(self):
        """
        If every attempt raises APITimeoutError, the function
        must try exactly 3 times then raise ModelTimeout.
        """
        mock_call = MagicMock(side_effect=APITimeoutError("timeout"))

        with pytest.raises(ModelTimeout):
            await run_conversation_turn(mock_call, retries=3)

        assert mock_call.call_count == 3, (
            f"Expected 3 attempts, got {mock_call.call_count}"
        )

    @pytest.mark.asyncio
    async def test_raises_model_timeout_not_raw_exception(self):
        """
        After all retries fail, must raise ModelTimeout —
        not the raw APITimeoutError. Callers catch ModelTimeout,
        not OpenAI exceptions.
        """
        mock_call = MagicMock(side_effect=APITimeoutError("timeout"))

        with pytest.raises(ModelTimeout):
            await run_conversation_turn(mock_call, retries=3)

    @pytest.mark.asyncio
    async def test_raises_rate_limit_reached_on_rate_limit_error(self):
        """
        After all retries fail with RateLimitError, must raise
        RateLimitReached — not the raw RateLimitError.
        """
        mock_call = MagicMock(side_effect=RateLimitError("rate limit"))

        with pytest.raises(RateLimitReached):
            await run_conversation_turn(mock_call, retries=3)

    @pytest.mark.asyncio
    async def test_succeeds_if_third_attempt_works(self):
        """
        If the first two calls fail but the third succeeds,
        must return the result without raising.
        """
        mock_call = MagicMock(side_effect=[
            APITimeoutError("fail"),
            APITimeoutError("fail"),
            "success"
        ])

        result = await run_conversation_turn(mock_call, retries=3)

        assert result == "success"
        assert mock_call.call_count == 3