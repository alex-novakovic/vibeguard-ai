import os
import json
import random
import logging
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError

# Importing your specific exception classes
from agent.exceptions import (
    RateLimitReached, 
    ModelTimeout, 
    ParsingFailed, 
    EmptyResponse
)
from agent.prompts.system_prompt import CONVERSATION_PROMPT, PARSING_PROMPT
from data.schemas import VisionDoc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("ScopingSession")

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "google/gemini-2.0-flash-lite-001")
PARSING_MODEL = os.getenv("PARSING_MODEL", "anthropic/claude-3-haiku")

class ScopingSession:
    """
    Encapsulates all state for one user's scoping conversation.
    """

    def __init__(self):
        self.chat_messages: list[dict] = []
        self.total_tokens: int = 0

    def _ensure_system_prompt(self):
        if not self.chat_messages:
            self.chat_messages.append({
                "role": "system",
                "content": CONVERSATION_PROMPT
            })

    def get_transcript(self) -> str:
        return "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in self.chat_messages
            if msg["role"] != "system"
        )

    async def _handle_backoff(self, attempt: int, error: Exception):
        """Implements exponential backoff with jitter."""
        wait = (2 ** attempt) + random.uniform(0, 1)
        if isinstance(error, RateLimitError):
            wait = 60 * (2 ** attempt) + random.uniform(0, 5)
            
        logger.warning(f"Retrying in {wait:.2f}s due to {type(error).__name__}: {error}")
        await asyncio.sleep(wait)

    async def run_conversation_turn(self, user_message: str, retries: int = 3) -> str:
        self._ensure_system_prompt()
        self.chat_messages.append({"role": "user", "content": user_message})

        for attempt in range(retries):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=CONVERSATION_MODEL,
                    messages=self.chat_messages,
                    temperature=0.7,
                    timeout=30.0 
                )

                assistant_message = response.choices[0].message.content
                
                if not assistant_message:
                    raise EmptyResponse("Model returned an empty response.")

                tokens = response.usage.total_tokens if response.usage else 0

                self.chat_messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })

                self.total_tokens += tokens
                return assistant_message

            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt < retries - 1:
                    await self._handle_backoff(attempt, e)
                else:
                    if isinstance(e, RateLimitError):
                        raise RateLimitReached("Rate limit hit after all retries.") from e
                    raise ModelTimeout("Model timed out after all retries.") from e

    async def scoping_session(self) -> dict:
        transcript = self.get_transcript()
        filled_prompt = PARSING_PROMPT.replace("{transcript}", transcript)

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=PARSING_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a precise data extraction engine. Return only valid JSON. No markdown, no explanation."
                        },
                        {
                            "role": "user",
                            "content": filled_prompt
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )

                raw = response.choices[0].message.content
                tokens = response.usage.total_tokens if response.usage else 0
                self.total_tokens += tokens

                if not raw:
                    raise EmptyResponse("AI returned an empty response body.")

                if raw.strip().startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                vision_doc = json.loads(raw)
                vision_doc["createdAt"] = datetime.now(timezone.utc).isoformat()

                return VisionDoc(**vision_doc)

            except (RateLimitError, APITimeoutError) as e:
                if attempt < 2:
                    await self._handle_backoff(attempt, e)
                else:
                    if isinstance(e, RateLimitError):
                        raise RateLimitReached("Rate limit hit during parsing.") from e
                    raise ModelTimeout("Model timed out during parsing.") from e
            except (json.JSONDecodeError, TypeError):
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    raise ParsingFailed("Failed to parse valid vision doc JSON.")
            except Exception as e:
                logger.exception("Unexpected error during scoping session")
                raise
