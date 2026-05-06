import gradio as gr
import json
from pathlib import Path

from agent.loop import run_agent, AgentSession, PHASE_GUARDIAN
from interfaces import StorageBackend
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

WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"


def on_startup():
    try:
        status, state = storage.load_or_create_project()
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
        return (
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc.model_dump(),
            state.feature_log,
            status,
            state,
        )
    return (
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        status,
        None,
    )


async def on_send(message, history, session, status, proj_state, initialized):
    def _agent_error(msg):
        err_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": msg},
        ]
        return err_history, err_history, "", gr.update(), gr.update(), initialized, status, proj_state

    try:
        response = await run_agent(message, status, proj_state, session)
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
        try:
            log_path = storage.initialize_feature_log(vision_doc)
            log_data = json.loads(Path(log_path).read_text())
            return history, history, "", vision_doc.model_dump(), log_data, True, "existing", session.project_state
        except (FileSystemError, ValueError) as e:
            err_history = history + [{"role": "assistant", "content": f"⚠️ Failed to save project files: {e}"}]
            return err_history, err_history, "", gr.update(), gr.update(), initialized, status, proj_state

    return history, history, "", gr.update(), gr.update(), initialized, status, proj_state


with gr.Blocks(title="VibeGuard AI") as demo:
    session_state     = gr.State(AgentSession())  # instance, not class
    history_state     = gr.State([])
    status_state      = gr.State("new")           # "new" | "existing" from load_or_create_project
    proj_state_state  = gr.State(None)            # ProjectState object from Member B
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
        inputs=[],
        outputs=[chatbot, vision_display, log_display, status_state, proj_state_state],
    )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)
