import os
import logging
from dotenv import load_dotenv
from data.logger import Logger
from openai import AsyncOpenAI

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

logger = Logger()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
# Silence noisy third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# LLM Configuration
CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "google/gemini-2.0-flash-lite-001")
PARSING_MODEL = os.getenv("PARSING_MODEL", "anthropic/claude-3-haiku")
