import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app import on_startup, on_send
from agent.agent_session import AgentSession, PHASE_SCOPING, PHASE_GUARDIAN
from data.state import ProjectState
from data.schemas import SessionLog
from utils.exceptions import (
    VibeGuardError,
    ParsingFailed,
    FileSystemError,
    RateLimitReached,
    ModelTimeout,
    EmptyResponse,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_state():
    state = ProjectState()
    state.session_log = SessionLog()
    state.feature_log = {"features": {}}
    state.vision_doc = MagicMock()
    state.vision_doc.model_dump.return_value = {}
    return state


# ── on_startup: error handling ────────────────────────────────────────────────

def test_on_startup_parsing_failed_returns_readable_message():
    with patch("app.storage.load_or_create_project", side_effect=ParsingFailed("bad json")):
        result = on_startup("user-1")
        chat = result[1]
        assert chat[0]["role"] == "assistant"
        assert "⚠️" in chat[0]["content"]


def test_on_startup_filesystem_error_returns_readable_message():
    with patch("app.storage.load_or_create_project", side_effect=FileSystemError("disk full")):
        result = on_startup("user-1")
        chat = result[1]
        assert "⚠️" in chat[0]["content"]


def test_on_startup_vibeguard_error_returns_readable_message():
    with patch("app.storage.load_or_create_project", side_effect=VibeGuardError("unexpected")):
        result = on_startup("user-1")
        chat = result[1]
        assert "⚠️" in chat[0]["content"]


def test_on_startup_error_does_not_crash():
    with patch("app.storage.load_or_create_project", side_effect=FileSystemError("fail")):
        try:
            on_startup("user-1")
        except Exception:
            pytest.fail("on_startup raised an exception instead of returning an error message")


def test_on_startup_error_returns_new_status():
    with patch("app.storage.load_or_create_project", side_effect=FileSystemError("fail")):
        result = on_startup("user-1")
        status = result[4]
        assert status == "new"


# ── on_startup: success ───────────────────────────────────────────────────────

def test_on_startup_new_project_returns_welcome_message():
    mock_state = _mock_state()
    with patch("app.storage.load_or_create_project", return_value=("new", mock_state)), \
         patch("app.storage.start_session", return_value=SessionLog()):
        result = on_startup("user-1")
        chat = result[1]
        assert chat[0]["role"] == "assistant"
        assert result[4] == "new"


def test_on_startup_new_project_returns_agent_session():
    mock_state = _mock_state()
    with patch("app.storage.load_or_create_project", return_value=("new", mock_state)), \
         patch("app.storage.start_session", return_value=SessionLog()):
        result = on_startup("user-1")
        session = result[6]
        assert isinstance(session, AgentSession)


def test_on_startup_existing_project_sets_guardian_phase():
    mock_state = _mock_state()
    with patch("app.storage.load_or_create_project", return_value=("existing", mock_state)), \
         patch("app.storage.start_session", return_value=SessionLog()):
        result = on_startup("user-1")
        session = result[6]
        assert session.phase == PHASE_GUARDIAN


def test_on_startup_existing_project_returns_existing_status():
    mock_state = _mock_state()
    with patch("app.storage.load_or_create_project", return_value=("existing", mock_state)), \
         patch("app.storage.start_session", return_value=SessionLog()):
        result = on_startup("user-1")
        assert result[4] == "existing"


# ── on_send: error handling ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_send_rate_limit_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        result = await on_send("hello", [], session, "new", None, False, MagicMock())
        error_msg = result[0][-1]
        assert error_msg["role"] == "assistant"
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_model_timeout_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=ModelTimeout()):
        result = await on_send("hello", [], session, "new", None, False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_empty_response_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=EmptyResponse()):
        result = await on_send("hello", [], session, "new", None, False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_vibeguard_error_returns_readable_message():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=VibeGuardError("fail")):
        result = await on_send("hello", [], session, "new", None, False, MagicMock())
        error_msg = result[0][-1]
        assert "⚠️" in error_msg["content"]


@pytest.mark.asyncio
async def test_on_send_error_does_not_crash():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        try:
            await on_send("hello", [], session, "new", None, False, MagicMock())
        except Exception:
            pytest.fail("on_send raised an exception instead of returning an error message")


@pytest.mark.asyncio
async def test_on_send_error_returns_original_status():
    session = AgentSession()
    with patch("app.agent.run_agent", new_callable=AsyncMock, side_effect=RateLimitReached()):
        result = await on_send("hello", [], session, "new", None, False, MagicMock())
        returned_status = result[6]
        assert returned_status == "new"