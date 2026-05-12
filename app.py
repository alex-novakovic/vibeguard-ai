import gradio as gr
import uuid
from agent.agent_session import AgentSession, PHASE_GUARDIAN
from agent.loop import Agent
from interfaces import StorageBackend, AgentFunctions
from data.storage import Storage
from utils.exceptions import (
    VibeGuardError,
    RateLimitReached,
    ModelTimeout,
    EmptyResponse,
    ParsingFailed,
    FileSystemError,
)

storage: StorageBackend = Storage()
agent: AgentFunctions = Agent()

_session_states: dict = {}

WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"


def on_startup(user_id, request: gr.Request):
    if not user_id:
        user_id = str(uuid.uuid4())  # first visit — generate once, stored in browser
    try:
        session = AgentSession()
        session.user_id = user_id
        status, state = storage.load_or_create_project(user_id)
        session_id, state.session_log = storage.start_session(state.session_log)
        _session_states[request.session_hash] = {}
        _session_states[request.session_hash]["session_id"] = session_id
    except ParsingFailed as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()
    except FileSystemError as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()
    except VibeGuardError as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()

    session.project_state = state
    _session_states[request.session_hash]["agent_session"] = session
    if status == "existing":
        session.phase = PHASE_GUARDIAN
        return (
            user_id,
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc.model_dump(),
            state.feature_log,
            state.session_log.model_dump() if state.session_log else None,
            status,
            session,
        )
    return (
        user_id,
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        None,
        status,
        session,
    )

def save_logs(session):
    if session is None or session.project_state is None:
        return gr.update()
    try:
        proj_state = session.project_state
        storage.dump_logs(proj_state.vision_doc, proj_state.feature_log, proj_state.session_log)
    except FileSystemError as e:
        return gr.update(value=f"⚠️ Auto-save failed: {e}")
    return gr.update()

def on_exit(request: gr.Request):
    entry = _session_states.pop(request.session_hash, None)
    if entry is None:
        return
    session_id = entry["session_id"]
    session = entry["agent_session"]
    if session is None or session.project_state is None:
        return
    try:
        proj_state = session.project_state
        proj_state.session_log = storage.end_session(
            session_id,
            proj_state.session_log,
            proj_state.feature_log,
            proj_state.current_cycle_tokens,
        )
        storage.dump_logs(proj_state.vision_doc, proj_state.feature_log, proj_state.session_log)
    except VibeGuardError:
        pass


async def on_send(message, history, session, status, initialized, request: gr.Request):
    def _agent_error(msg):
        err_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": msg},
        ]
        return err_history, err_history, "", gr.update(), gr.update(), gr.update(), initialized, status, session

    try:
        response, session = await agent.run_agent(message, status, session)
    except RateLimitReached:
        return _agent_error("⚠️ Rate limit reached. Please wait a moment and try again.")
    except ModelTimeout:
        return _agent_error("⚠️ The AI took too long to respond. Please try again.")
    except EmptyResponse:
        return _agent_error("⚠️ The AI returned an empty response. Please try again.")
    except ParsingFailed:
        return _agent_error("⚠️ Failed to parse the AI's response. Please try again.")
    except VibeGuardError as e:
        return _agent_error(f"⚠️ An error occurred: {e}")

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]
    if session.phase == PHASE_GUARDIAN:
        proj_state = session.project_state
        prev = proj_state.previous_feature_id
        active = proj_state.active_feature_id

        if not initialized:
            proj_state.feature_log = storage.initialize_feature_log(proj_state.vision_doc)
            _session_states[request.session_hash]["agent_session"] = session
            session_log_dump = proj_state.session_log.model_dump() if proj_state.session_log else None
            return history, history, "", proj_state.vision_doc.model_dump(), proj_state.feature_log, session_log_dump, True, "existing", session

        if prev is None and active is not None:
            proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "start", None, None)
        elif prev == active:
            if session.drift_note is not None and session.alignment_note is not None:
                proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", session.alignment_note, session.drift_note)
            elif session.alignment_note is not None:
                proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", session.alignment_note, None)
            elif session.drift_note is not None:
                proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", None, session.drift_note)
        elif prev is not None and active is None:
            proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, prev, "complete", session.alignment_note, None)

        session_log_dump = proj_state.session_log.model_dump() if proj_state.session_log else None
        _session_states[request.session_hash]["agent_session"] = session
        return history, history, "", gr.update(), proj_state.feature_log, session_log_dump, initialized, status, session

    return history, history, "", gr.update(), gr.update(), gr.update(), initialized, status, session


with gr.Blocks(title="VibeGuard AI") as demo:
    user_id_browser   = gr.BrowserState(None)
    session_state     = gr.State(None)
    history_state     = gr.State([])
    status_state      = gr.State("new")           # "new" | "existing" from load_or_create_project
    initialized_state = gr.State(False)           # True after initialize_feature_log is called

    gr.Markdown("# VibeGuard AI\n*Stop tinkering. Start shipping.*")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                label="Agent",
                height=500,
                buttons=["copy"],
                autoscroll=True,
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type here and press Enter…",
                    show_label=False,
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Column(scale=1, min_width=300):
            with gr.Accordion("Vision Document", open=False):
                vision_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Feature Log", open=False):
                log_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Session Log", open=False):
                session_display = gr.JSON(label=None, value=None)

    _send_inputs  = [msg_input, history_state, session_state, status_state, initialized_state]
    _send_outputs = [chatbot, history_state, msg_input, vision_display, log_display, session_display, initialized_state, status_state, session_state]

    send_btn.click(on_send, inputs=_send_inputs, outputs=_send_outputs)
    msg_input.submit(on_send, inputs=_send_inputs, outputs=_send_outputs)
    demo.load(
        on_startup,
        inputs=[user_id_browser],
        outputs=[user_id_browser, chatbot, vision_display, log_display, session_display, status_state, session_state],
    )
    gr.Timer(300).tick(save_logs, inputs=[session_state], outputs=[chatbot])
    demo.unload(on_exit)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)
