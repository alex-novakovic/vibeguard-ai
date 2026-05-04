import os
import time
import json
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from agent.prompts.system_prompt import CONVERSATION_PROMPT, PARSING_PROMPT
from agent.prompts.pydantic_schemas import VisionDoc
from data.validate import validate_vision_doc
import asyncio

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)


class ScopingSession:
    """
    Encapsulates all state for one user's scoping conversation.
    Replaces the global chat_messages list.
    One instance per user — no shared state between users.
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

    async def run_conversation_turn(self, user_message: str, retries: int = 3) -> tuple[str, int]:
        """
        Sends one message, gets one response.
        Returns (response_text, tokens_used).
        """
        self._ensure_system_prompt()
        self.chat_messages.append({"role": "user", "content": user_message})

        for attempt in range(retries):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model="google/gemini-2.0-flash-lite-001",
                    messages=self.chat_messages,
                    temperature=0.7,
                )

                assistant_message = response.choices[0].message.content
                tokens = response.usage.total_tokens if response.usage else 0

                self.chat_messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })

                self.total_tokens += tokens
                return assistant_message

            except RateLimitError:
                if attempt < retries - 1:
                    wait = 60 * (2 ** attempt) + random.uniform(0, 5)
                    print(f"Rate limit hit, retrying in {wait:.1f}s... (attempt {attempt + 1}/{retries})")
                    await asyncio.sleep(wait)
                else:
                    raise

    async def scoping_session(self) -> dict:
        """
        Parses the completed conversation into a structured vision doc.
        Called once when scoping is complete.
        """
        transcript = self.get_transcript()
        filled_prompt = PARSING_PROMPT.replace("{transcript}", transcript)

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model="anthropic/claude-3-haiku",
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
                    raise ValueError("Empty response.")

                if raw.strip().startswith("```"):
                    raw = raw.split("\n", 1)[-1]
                    raw = raw.rsplit("```", 1)[0]

                vision_doc = json.loads(raw)
                vision_doc["createdAt"] = datetime.now(timezone.utc).isoformat()

                validate_vision_doc(vision_doc)
                return vision_doc

            except RateLimitError:
                if attempt < 2:
                    wait = 60 * (2 ** attempt) + random.uniform(0, 5)
                    print(f"Rate limit hit, retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                else:
                    raise
            except (json.JSONDecodeError, Exception) as e:
                if attempt < 2:
                    print(f"Parsing failed, retrying... ({e})")
                    await asyncio.sleep(5)
                else:
                    raise ValueError(f"Failed to parse vision_doc after {attempt + 1} attempts: {e}")