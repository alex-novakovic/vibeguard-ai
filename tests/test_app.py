import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app import on_startup, on_send
from agent.agent_session import AgentSession, PHASE_SCOPING, PHASE_GUARDIAN
from data.state import ProjectState
from utils.exceptions import (
    VibeGuardError,
    ParsingFailed,
    DatabaseError,
    RateLimitReached,
    ModelTimeout,
    EmptyResponse,
)

def _mock_state():
    state = ProjectState()
    state.session_log = []
    state.feature_log = []
    state.vision_doc = MagicMock()
    state.vision_doc.model_dump.return_value = {}
    state.vision_doc.model_dump_json.return_value = "{}"
    return state


def _mock_session_entry():
    entry = MagicMock()
    entry.workSessionId = "test-session-id"
    entry.model_dump_json.return_value = "{}"
    return entry


def _mock_request():
    req = MagicMock()
    req.session_hash = "test-hash"
    return req

@pytest.mark.asyncio
async def test_on_startup_parsing_failed_returns_readable_message():
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, side_effect=ParsingFailed("bad json")):
        result = await on_startup("user-1", _mock_request())
        chat = result[1]
        assert chat[0]["role"] == "assistant"
        assert "⚠️" in chat[0]["content"]


@pytest.mark.asyncio
async def test_on_startup_database_error_returns_readable_message():
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, side_effect=DatabaseError("db fail")):
        result = await on_startup("user-1", _mock_request())
        chat = result[1]
        assert "⚠️" in chat[0]["content"]


@pytest.mark.asyncio
async def test_on_startup_vibeguard_error_returns_readable_message():
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, side_effect=VibeGuardError("unexpected")):
        result = await on_startup("user-1", _mock_request())
        chat = result[1]
        assert "⚠️" in chat[0]["content"]


@pytest.mark.asyncio
async def test_on_startup_error_does_not_crash():
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, side_effect=DatabaseError("fail")):
        try:
            await on_startup("user-1", _mock_request())
        except Exception:
            pytest.fail("on_startup raised an exception instead of returning an error message")


@pytest.mark.asyncio
async def test_on_startup_error_returns_new_status():
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, side_effect=DatabaseError("fail")):
        result = await on_startup("user-1", _mock_request())
        assert result[5] == "new"


@pytest.mark.asyncio
async def test_on_startup_new_project_returns_welcome_message():
    mock_state = _mock_state()
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, return_value=("new", mock_state)), \
         patch("app.storage.start_session", new_callable=AsyncMock, return_value=_mock_session_entry()):
        result = await on_startup("user-1", _mock_request())
        chat = result[1]
        assert chat[0]["role"] == "assistant"
        assert result[5] == "new"


@pytest.mark.asyncio
async def test_on_startup_new_project_returns_agent_session():
    mock_state = _mock_state()
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, return_value=("new", mock_state)), \
         patch("app.storage.start_session", new_callable=AsyncMock, return_value=_mock_session_entry()):
        result = await on_startup("user-1", _mock_request())
        assert isinstance(result[6], AgentSession)


@pytest.mark.asyncio
async def test_on_startup_existing_project_sets_guardian_phase():
    mock_state = _mock_state()
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, return_value=("existing", mock_state)), \
         patch("app.storage.start_session", new_callable=AsyncMock, return_value=_mock_session_entry()):
        result = await on_startup("user-1", _mock_request())
        session = result[6]
        assert session.phase == PHASE_GUARDIAN


@pytest.mark.asyncio
async def test_on_startup_existing_project_returns_existing_status():
    mock_state = _mock_state()
    with patch("app.init_db", new_callable=AsyncMock), \
         patch("app.storage.load_or_create_project", new_callable=AsyncMock, return_value=("existing", mock_state)), \
         patch("app.storage.start_session", new_callable=AsyncMock, return_value=_mock_session_entry()):
        result = await on_startup("user-1", _mock_request())
        assert result[5] == "existing"

@pytest.mark.asyncio
async def test_on_send_rate_limit_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        result = await on_send("hello", [], session, "new", False, MagicMock())
        error_msg = result[0][-1]
        assert error_msg["role"] == "assistant"
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_model_timeout_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=ModelTimeout()):
        result = await on_send("hello", [], session, "new", False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_empty_response_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=EmptyResponse()):
        result = await on_send("hello", [], session, "new", False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_vibeguard_error_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=VibeGuardError("fail")):
        result = await on_send("hello", [], session, "new", False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_error_does_not_crash():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        try:
            await on_send("hello", [], session, "new", False, MagicMock())
        except Exception:
            pytest.fail("on_send raised an exception instead of returning an error message")


@pytest.mark.asyncio
async def test_on_send_error_returns_original_status():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        result = await on_send("hello", [], session, "new", False, MagicMock())
        assert result[7] == "new"
