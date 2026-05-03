# Code-review

* Author: Pavel Katurov (katurov)
* Date: 2024-06-03 from 7 am till 8 am

The team has done a great job building a well-balanced prototype. You have a strong **"Brain"** (logic and prompts), a reliable **"Skeleton"** (data validation), and functional **"Hands"** (the interface). The project shows great promise, but moving to a professional, production-ready level requires a significant shift in engineering discipline.

## 1. Architecture & System Design
*   **Phase Separation (Scoping & Guardian):** This is your primary architectural advantage. Clearly decoupling requirement gathering from the maintenance process allows the system to scale easily and accommodate new agent modes.
*   **Critical Area: State Management.** Currently, the `agent/scoping.py` and `loop.py` modules rely heavily on global variables (`agent_state`, `chat_messages`). 
    *   **The Issue:** This is a "time bomb" for scalability. The application cannot scale horizontally; if two users launch the agent simultaneously, their data will collide and overwrite each other. Furthermore, global state makes the code nearly impossible to unit test.
    *   **The Solution:** Immediate transition to an Object-Oriented (OOP) approach. All session context must be encapsulated within classes (e.g., `AgentSession`). This will allow you to swap storage backends (e.g., from in-memory to a database) without refactoring the core logic.

## 2. Code Quality & Engineering Standards
*   **Data Validation:** Using Pydantic is an excellent choice. However, there is currently a "conflict of interest" in the project: some logic uses Pydantic, while other parts rely on manual dictionary checks. You must establish Pydantic schemas as the **single source of truth** for the entire project.
*   **Asynchrony (Asyncio):** We are working with LLMs, which involve slow network I/O. In a modern web service, asynchrony is non-negotiable.
    *   **Why it matters:** When you use synchronous code (or basic `threading`), your server literally "sleeps" while waiting for an API response. Transitioning to `async def` and `await` allows the server to handle hundreds of concurrent requests without making users wait for one another.
*   **Error Handling:** Move away from broad `except Exception` blocks and simple print statements. Utilize the `logging` library and implement specific handling for LLM failure modes (API timeouts, Rate Limits, malformed JSON) using **retry mechanisms** with exponential backoff.

## 3. Prompt Engineering
*   This is the strongest aspect of the current codebase. The prompts (`CONVERSATION_PROMPT`, `PARSING_PROMPT`) are meticulously crafted and utilize advanced techniques like "Atomic Interaction" and "The Experience Wall."

## 4. Technical Debt & Qualification
*   **Testing:** The `tests/` directory is empty. Please note: comprehensive automated testing is a **qualification requirement** for this course. Any project processing unpredictable LLM outputs must be covered by unit tests and integration tests using **Mocks** for API responses.
*   **CI/CD Pipeline:** The project has matured enough for automation. Set up GitHub Actions to automatically run tests and linters (e.g., `ruff`) on every push. This prevents "broken" code from reaching the main branch.
*   **Hardcoding**: Model identifiers (`gemini-2.0-flash-lite`, `claude-3-haiku`) and provider settings are hardcoded into the logic. These should be moved to configuration files or a `.env` file.


## Individual Recommendations

### 👑 Isidora (Agent Logic & Prompt Engineering)
*   **Engineering Discipline:** Your code in `agent/scoping.py` needs refactoring. Transition to a `ScopingSession` class to encapsulate message history and move away from global state. This is fundamental for user data security.
*   **Growth Path:** Explore the **LangGraph** library. Your phase-switching logic maps perfectly to graph-based concepts, which would significantly simplify the maintenance of `loop.py` and make agent behavior more predictable.

### 🛠 Alex (Infrastructure & UI)
*   **Code Cleanliness:** There is a lot of "dead code" and placeholders (STUBS) in your commits. Aim to clean up branches before pushing. Use Abstract Base Classes (`abc.ABC`) to define interfaces—this is the professional way to establish architecture for the team.
*   **Tech Stack:** Refactor the Gradio integration to be fully asynchronous (`asyncio`). Looking ahead, study **FastAPI**—if the project outgrows Gradio, you will need a robust and high-performance API layer.

### 📐 Milica (Data Integrity & Validation)
*   **Tooling:** Your manual validation is reliable, but industry standard is **Pydantic**. It automates checks via type annotations and is significantly faster. Try to merge your validation logic with Isidora’s schemas.
*   **Testing:** Reliability is your domain. Start writing `pytest` suites for every edge case (empty backlogs, incorrect data types). A project cannot be considered complete without a verified test suite.
*   **Growth Path:** Study **SQLAlchemy** or **Beanie**. Storing data in JSON files is a good start, but the project will soon require a proper database with migration support.

---

**Final Verdict:** This is a very strong and well-balanced team. If you clean up the data architecture, transition to asynchronous I/O, and resolve the testing debt, this project will become a professional-grade tool. Happy refactoring!