import gradio as gr
import json
from pathlib import Path

from agent.loop import run_agent, AgentSession, PHASE_GUARDIAN
from interfaces import StorageBackend
from dev_backends import FakeStorage

# ── backend injection — swap when Member A/B deliver ─────────────────────────
storage: StorageBackend = FakeStorage()

WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"


def on_startup():
    status, state = storage.load_or_create_project()
    if status == "existing":
        return (
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc,
            state.feature_log,
            "active",
        )
    return (
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        "scoping",
    )


async def on_send(message, history, session: AgentSession):
    status, state = storage.load_or_create_project()
    response = await run_agent(message, status, state, session)

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]
    
    if session.phase == PHASE_GUARDIAN and session.project_state:
        vision_doc = session.project_state.vision_doc
        log_path = storage.initialize_feature_log(vision_doc.model_dump())
        log_data = json.loads(Path(log_path).read_text())
        return history, history, "", vision_doc, log_data

    return history, history, "", gr.update(), gr.update()


with gr.Blocks(title="VibeGuard AI") as demo:
    session_state = gr.State(AgentSession)
    history_state = gr.State([])
    phase_state   = gr.State("scoping")

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

    send_btn.click(
        on_send,
        inputs=[msg_input, history_state, session_state],
        outputs=[chatbot, history_state, msg_input, vision_display, log_display],
    )
    msg_input.submit(
        on_send,
        inputs=[msg_input, history_state, session_state],
        outputs=[chatbot, history_state, msg_input, vision_display, log_display],
    )
    demo.load(
        on_startup,
        inputs=[],
        outputs=[chatbot, vision_display, log_display, phase_state],
    )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)