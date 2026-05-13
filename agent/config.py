import os
import logging
from openai import OpenAI
from dotenv import load_dotenv
from data.logger import Logger

load_dotenv()

# 1. Centralized System Logging Configuration
# This ensures all modules follow the same format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
# Silence noisy third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# 2. LLM Configuration
CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "google/gemini-2.0-flash-lite-001")
PARSING_MODEL = os.getenv("PARSING_MODEL", "anthropic/claude-3-haiku")

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

logger = Logger()