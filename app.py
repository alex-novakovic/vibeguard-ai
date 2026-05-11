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


def on_startup(user_id):
    if not user_id:
        user_id = str(uuid.uuid4())  # first visit — generate once, stored in browser
    try:
        status, state = storage.load_or_create_project(user_id)
        state.session_log = storage.start_session(state.session_log)
        session = AgentSession()
        session.user_id = user_id
        session.project_state = state
    except ParsingFailed as e:
        msg = f"⚠️ Saved project files are corrupted and could not be loaded: {e}"
        return [{"role": "assistant", "content": msg}], None, None, "new", None
    except FileSystemError as e:
        msg = f"⚠️ Failed to read project files from disk: {e}"
        return [{"role": "assistant", "content": msg}], None, None, "new", None
    except VibeGuardError as e:
        msg = f"⚠️ Unexpected error on startup: {e}"
        return [{"role": "assistant", "content": msg}], None, None, "new", None

    if status == "existing":
        session.phase = PHASE_GUARDIAN
        return (
            user_id,
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc.model_dump(),
            state.feature_log,
            status,
            state,
            session,
        )
    return (
        user_id,
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        status,
        state,
        session,
    )

def save_logs(proj_state, request: gr.Request):
    if proj_state is None:
        return gr.update()
    _session_states[request.session_hash] = proj_state
    try:
        storage.dump_logs(proj_state.vision_doc, proj_state.feature_log, proj_state.session_log)
    except FileSystemError as e:
        return gr.update(value=f"⚠️ Auto-save failed: {e}")
    return gr.update()

def on_exit(request: gr.Request):
    proj_state = _session_states.pop(request.session_hash, None)
    if proj_state is None:
        return
    try:
        storage.dump_logs(proj_state.vision_doc, proj_state.feature_log, proj_state.session_log)
    except FileSystemError:
        pass


async def on_send(message, history, session, status, proj_state, initialized, request: gr.Request):
    def _agent_error(msg):
        err_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": msg},
        ]
        return err_history, err_history, "", gr.update(), gr.update(), initialized, status, proj_state

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

    if session.phase == PHASE_GUARDIAN and session.project_state and not initialized:
        vision_doc = session.project_state.vision_doc
        log_data = storage.initialize_feature_log(vision_doc)
        session.project_state.feature_log = log_data
        _session_states[request.session_hash] = session.project_state
        return history, history, "", vision_doc.model_dump(), log_data, True, "existing", session.project_state

    return history, history, "", gr.update(), gr.update(), initialized, status, proj_state


with gr.Blocks(title="VibeGuard AI") as demo:
    user_id_browser   = gr.BrowserState(None)
    session_state     = gr.State(None)
    history_state     = gr.State([])
    status_state      = gr.State("new")           # "new" | "existing" from load_or_create_project
    proj_state_state  = gr.State(None)                                             # ProjectState object from Member B
    initialized_state = gr.State(False)           # True after initialize_feature_log is called

    gr.Markdown("# VibeGuard AI\n*Stop tinkering. Start shipping.*")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                label="Agent",
                height=500,
                buttons=["copy"],
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
            with gr.Accordion("Vision Document", open=True):
                vision_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Feature Log", open=True):
                log_display = gr.JSON(label=None, value=None)

    _send_inputs  = [msg_input, history_state, session_state, status_state, proj_state_state, initialized_state]
    _send_outputs = [chatbot, history_state, msg_input, vision_display, log_display, initialized_state, status_state, proj_state_state]

    send_btn.click(on_send, inputs=_send_inputs, outputs=_send_outputs)
    msg_input.submit(on_send, inputs=_send_inputs, outputs=_send_outputs)
    demo.load(
        on_startup,
        inputs=[user_id_browser],
        outputs=[user_id_browser, chatbot, vision_display, log_display, status_state, proj_state_state, session_state],
    )
    gr.Timer(300).tick(save_logs, inputs=[proj_state_state], outputs=[chatbot])
    demo.unload(on_exit)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)
