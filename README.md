# VibeGuard AI

> *Stop tinkering. Start shipping.*

VibeGuard AI is a conversational AI assistant for solo developers. It runs a structured scoping session to turn a vague idea into a realistic, time-boxed project plan — then guards that plan against scope creep as you build.

---

## How it works

The agent operates in two phases:

**1. Scoping** — A multi-turn conversation guided by Gemini 2.0 Flash extracts your vision, time budget, experience level, tech stack, and feature list. When all fields are confirmed, a second LLM call (Claude 3 Haiku) parses the transcript into a validated `VisionDoc` JSON document.

**2. Guardian** — Once scoping is complete, the agent tracks feature progress, detects drift from your original plan, suggests the next task, and warns when token usage per feature or session exceeds healthy thresholds.

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
MONGODB_URL=your_mongodb_connection_string_here
CONVERSATION_MODEL=google/gemini-2.0-flash-lite-001
PARSING_MODEL=anthropic/claude-3-haiku
```

Get your OpenRouter API key from [openrouter.ai/keys](https://openrouter.ai/keys).  
Get your MongoDB connection string from [mongodb.com/atlas](https://www.mongodb.com/atlas) (free tier works).  
`CONVERSATION_MODEL` and `PARSING_MODEL` are optional — the values above are the defaults.

### 5. Run the app

```bash
python app.py
```

The Gradio interface will open at `http://localhost:7860`.

---

## Project structure

```
vibeguard-ai/
├── app.py                        # Gradio UI and event handlers
├── interfaces.py                 # Abstract base classes (StorageBackend, AgentFunctions, LoggerBackend)
├── requirements.txt
│
├── agent/
│   ├── loop.py                   # LangGraph graph definition and Agent class
│   ├── agent_session.py          # Per-user session state
│   ├── agent_utils.py            # classify_guardian_intent, generate_guardian_response
│   ├── config.py                 # OpenRouter client, logger, model constants
│   ├── scoping.py                # ScopingSession: conversation loop + transcript parsing
│   ├── drift.py                  # Drift detection flow
│   ├── complete.py               # Feature completion flow
│   ├── start_feature.py          # Feature start + feature ID extraction
│   ├── suggestion.py             # Next-task suggestion
│   └── prompts/
│       ├── system_prompt.py      # CONVERSATION_PROMPT and PARSING_PROMPT
│       ├── guardian_prompt.py    # Guardian system prompt
│       ├── classify_guardian_intent_prompt.py  # Intent classification prompt
│       ├── alignment_prompt.py   # Alignment checking prompt
│       ├── drift_prompt.py       # Drift detection prompt
│       └── suggestion_prompt.py  # Next-task suggestion prompt
│
├── data/
│   ├── schemas.py                # Pydantic/Beanie models: VisionDoc, FeatureLogItem, SessionEntry, LLMCallLog
│   ├── state.py                  # ProjectState class
│   ├── storage.py                # Storage class: load, save, log feature cycles, sessions
│   ├── db.py                     # MongoDB/Beanie initialisation (init_db)
│   └── logger.py                 # Logger class: inserts LLM call records into MongoDB
│
├── utils/
│   ├── exceptions.py             # Custom exception hierarchy (VibeGuardError and subtypes)
│   └── common.py                 # Shared helpers (timezone-aware timestamps)
│
└── tests/
    ├── conftest.py               # Shared pytest fixtures
    ├── test_agent.py             # Agent logic: scoping detection, state machine, retries
    ├── test_app.py               # App layer: startup, send, error handling
    ├── test_storage.py           # Data layer: Pydantic validation, ProjectState init
    ├── test_scoping.py           # (empty)
    ├── test_drift.py             # (empty)
    ├── test_integration.py       # (empty)
    └── eval/
        ├── eval_scoping.py
        ├── eval_drift.py
        ├── eval_alignment.py
        ├── eval_suggest_next_task.py
        ├── eval_classify_guardian_intent.py
        └── eval_extract_feature_from_id.py
```

---

## Architecture

```
User (Gradio UI)
       │
       ▼
  on_startup()  ──►  init_db()
                      storage.load_or_create_project()
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
                            └── guardian_node()
                                    │
                                    ├── classify_guardian_intent()   SUGGEST | START | COMPLETE | CHAT
                                    ├── suggest_next_task()
                                    ├── start_feature()
                                    ├── handle_completion_flow()     multi-turn completion check
                                    ├── handle_drift_flow()          periodic drift check (every 30 min)
                                    └── generate_guardian_response()
       │
       ▼
  token_check()                 →  Gradio warning if >50k tokens/feature or >100k tokens/session
  storage.log_feature_cycle()
  storage.dump_logs()           →  MongoDB (saves VisionDoc, FeatureLogItem, SessionEntry)
  Logger.log_llm_call()         →  MongoDB (LLMCallLog collection)
```

### Key design decisions

| Decision | Reason |
|---|---|
| LangGraph for orchestration | Explicit, typed state machine — phases are graph nodes, not if/elif chains |
| Pydantic + Beanie for all data schemas | Validates LLM output at the boundary; Beanie provides async MongoDB ODM with zero extra mapping |
| MongoDB as primary storage | Per-user documents survive restarts and are accessible across deployments |
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

## Data storage

All runtime data is persisted in **MongoDB**:

| Collection | Contents |
|---|---|
| `VisionDoc` | Validated project plan produced after scoping |
| `FeatureLogItem` | Per-feature status, work cycles, alignment notes, and drift events |
| `SessionEntry` | Session start/end times, token usage, features completed |
| `LLMCallLog` | Record of every LLM call with function name, prompt, response, and token count |

The app saves to MongoDB on every message and on tab close (`on_exit`).
