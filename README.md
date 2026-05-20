# VibeGuard AI

> *Stop tinkering. Start shipping.*

VibeGuard AI is a conversational AI assistant for solo developers. It runs a structured scoping session to turn a vague idea into a realistic, time-boxed project plan — then guards that plan against scope creep as you build.

---

## How it works

The agent operates in two phases:

**1. Scoping** — A multi-turn conversation guided by Gemini 2.0 Flash extracts your vision, time budget, experience level, tech stack, and feature list. When all fields are confirmed, a second LLM call (Claude 3 Haiku) parses the transcript into a validated `VisionDoc` JSON document.

**2. Guardian** — Once scoping is complete, the agent tracks feature progress, detects when you drift from your original plan, and suggests the next task to work on.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/vibeguard-ai.git
cd vibeguard-ai
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** Gradio must be exactly `6.14.0` and LangGraph must be exactly `1.1.10`. Other versions are not tested and may break the UI event wiring or graph compilation.

### 4. Configure environment variables

Create a `.env` file in the project root (it is gitignored and must never be committed):

```
OPENROUTER_API_KEY=your_openrouter_key_here
CONVERSATION_MODEL=google/gemini-2.0-flash-lite-001
PARSING_MODEL=anthropic/claude-3-haiku
```

Get your API key from [openrouter.ai/keys](https://openrouter.ai/keys).  
`CONVERSATION_MODEL` and `PARSING_MODEL` are optional — the values above are the defaults.

### 5. Run the app

```bash
python app.py
```

The Gradio interface will open at `http://localhost:7860`.

---

## Project structure

```
vibeguard-refactor/
├── app.py                        # Gradio UI and event handlers
├── interfaces.py                 # Abstract base classes (StorageBackend, AgentFunctions, LoggerBackend)
├── requirements.txt
│
├── agent/
│   ├── loop.py                   # LangGraph graph definition and Agent class
│   ├── agent_session.py          # Per-user session state
│   ├── scoping.py                # ScopingSession: conversation loop + transcript parsing
│   ├── alignment.py              # (in progress) alignment checking
│   ├── drift.py                  # (in progress) drift detection
│   ├── suggestion.py             # (in progress) next-task suggestion
│   └── prompts/
│       └── system_prompt.py      # CONVERSATION_PROMPT and PARSING_PROMPT
│
├── data/
│   ├── schemas.py                # Pydantic models: VisionDoc, BacklogItem, SessionLog, etc.
│   ├── state.py                  # ProjectState class
│   ├── storage.py                # Storage class: load, save, log feature cycles, sessions
│   ├── logger.py                 # Logger class: appends LLM call records to llm_calls.log
│   ├── wakatime.py               # (placeholder)
│   └── logs/                     # Auto-created at runtime (gitignored)
│       ├── vision_doc.json
│       ├── feature_log.json
│       ├── session_log.json
│       └── llm_calls.log
│
├── utils/
│   └── exceptions.py             # Custom exception hierarchy (VibeGuardError and subtypes)
│
└── tests/
    ├── test_agent.py             # Agent logic: scoping detection, state machine, retries
    ├── test_app.py               # App layer: startup, send, error handling
    ├── test_storage.py           # Data layer: Pydantic validation, ProjectState init
    ├── test_scoping.py           # (empty)
    ├── test_drift.py             # (empty)
    └── test_integration.py       # (empty)
```

---

## Architecture

```
User (Gradio UI)
       │
       ▼
  on_startup()  ──►  storage.load_or_create_project()
                      storage.start_session()
       │
       ▼
  on_send()  [per message]
       │
       ▼
  Agent.run_agent()  ──►  LangGraph graph
                            │
                            ├── route_entry()         phase: scoping | guardian
                            │
                            ├── scoping_node()        Gemini Flash, 3x retry + backoff
                            │       │
                            │       └── detect_scoping_complete()
                            │               │
                            │               └── finish_scoping_node()
                            │                       Claude Haiku → JSON → VisionDoc (Pydantic)
                            │
                            └── guardian_node()       (in progress)
       │
       ▼
  storage.initialize_feature_log()
  storage.dump_logs()               →  data/logs/*.json
  Logger.log_llm_call()             →  data/logs/llm_calls.log
```

### Key design decisions

| Decision | Reason |
|---|---|
| LangGraph for orchestration | Explicit, typed state machine — phases are graph nodes, not if/elif chains |
| Pydantic for all data schemas | Validates LLM output at the boundary; any field error raises before bad data is saved |
| Two-model pipeline | Gemini Flash for fast conversation; Claude Haiku at `temperature=0` for precise JSON extraction |
| Custom exception hierarchy | All failures map to a `VibeGuardError` subtype — the UI catches these and shows a clean `⚠️` message, never a traceback |
| Session-scoped state | `AgentSession` is created per user; no global mutable state, safe for concurrent users |

---

## Running tests

```bash
pytest tests/ -v
```

For async tests to work, `pytest-asyncio` must be installed (included in `requirements.txt`).

---

## Logs

All runtime data is written to `data/logs/` (created automatically, gitignored):

| File | Contents |
|---|---|
| `vision_doc.json` | Validated project plan produced after scoping |
| `feature_log.json` | Per-feature status, work cycles, and drift events |
| `session_log.json` | Session start/end times, token usage, features completed |
| `llm_calls.log` | Append-only record of every LLM call with prompt, response, and token count |

The app auto-saves every 5 minutes and performs a final save when the browser tab is closed.
