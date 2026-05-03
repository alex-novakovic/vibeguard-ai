import gradio as gr
import json
from pathlib import Path

from agent.loop import run_agent, agent_state, PHASE_GUARDIAN
from interfaces import AgentFunctions, StorageBackend
from dev_backends import DevProjectState, FakeAgentFunctions, FakeStorage

# ── backend injection — swap these two lines when Member A/B deliver ──────────
storage: StorageBackend = FakeStorage()
agent: AgentFunctions = FakeAgentFunctions()

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


def on_send(message, history):
    status, state = storage.load_or_create_project()
    response = run_agent(message, status, state)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]

    if agent_state["phase"] == PHASE_GUARDIAN:
        vision_doc = agent_state["project_state"].vision_doc
        log_path = storage.initialize_feature_log(vision_doc)
        log_data = json.loads(Path(log_path).read_text())
        return history, history, "", vision_doc, log_data

    return history, history, "", gr.update(), gr.update()


with gr.Blocks(title="VibeGuard AI") as demo:
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
        inputs=[msg_input, history_state],
        outputs=[chatbot, history_state, msg_input, vision_display, log_display],
    )
    msg_input.submit(
        on_send,
        inputs=[msg_input, history_state],
        outputs=[chatbot, history_state, msg_input, vision_display, log_display],
    )
    demo.load(
        on_startup,
        inputs=[],
        outputs=[chatbot, vision_display, log_display, phase_state],
    )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)
