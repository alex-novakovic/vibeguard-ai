import os
import time
import json
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from agent.prompts.system_prompt import CONVERSATION_PROMPT, PARSING_PROMPT
from agent.prompts.pydantic_schemas import VisionDoc

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

chat_messages = []

# TODO: call log_llm_call() here once Member B defines the signature
# from data.logger import log_llm_call
# log_llm_call(...)

def run_conversation_turn(user_message: str, retries: int = 3) -> str:
    global chat_messages

    if not chat_messages:
        chat_messages.append({
            "role": "system",
            "content": CONVERSATION_PROMPT
        })

    chat_messages.append({
        "role": "user",
        "content": user_message
    })

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-lite-001",
                messages=chat_messages,
                temperature=0.7,
            )

            assistant_message = response.choices[0].message.content

            # TODO: log_llm_call() here

            chat_messages.append({
                "role": "assistant",
                "content": assistant_message
            })

            return assistant_message

        except RateLimitError as e:
            if attempt < retries - 1:
                wait = 60 * (2 ** attempt) + random.uniform(0, 5)
                print(f"Rate limit hit, retrying in {wait:.1f}s... (attempt {attempt + 1}/{retries})")
                time.sleep(wait)
            else:
                raise


def scoping_session() -> dict:
    transcript = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in chat_messages
        if msg["role"] != "system"
    )

    filled_prompt = PARSING_PROMPT.replace("{transcript}", transcript)

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="anthropic/claude-3-haiku",
                messages=[
                {
                    "role": "system",
                    "content": f"""You are a precise data extraction engine.
                      Return only valid JSON. No markdown, no explanation."""
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

            # TODO: log_llm_call() here

            if not raw:
                raise ValueError("Empty response.")

            if raw.strip().startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]

            vision_doc = json.loads(raw)

            validated = VisionDoc(**vision_doc)
            result = validated.model_dump()
            result["createdAt"] = datetime.now(timezone.utc).isoformat()
            
    
            # with open("agent/output/vision_doc.json", "w") as f:
              #  json.dump(result, f, indent=2)

            return result

        except RateLimitError as e:
            if attempt < 2:
                wait = 60 * (2 ** attempt) + random.uniform(0, 5)
                print(f"Rate limit hit, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise
        except (json.JSONDecodeError, Exception) as e:
            if attempt < 2:
                print(f"Parsing failed, retrying... ({e})")
                time.sleep(5)
            else:
                raise ValueError(f"Failed to parse vision_doc after {attempt + 1} attempts: {e}")