import os
from beanie import init_beanie
from pymongo import AsyncMongoClient
from dotenv import load_dotenv
from data.schemas import VisionDoc, FeatureLogItem, SessionEntry, LLMCallLog

load_dotenv()

_client = None

async def init_db():
    global _client
    mongo_uri = os.getenv("MONGODB_URI")
    _client = AsyncMongoClient(mongo_uri)
    
    await init_beanie(
        database=_client.vibeguard,
        document_models=[VisionDoc, FeatureLogItem, SessionEntry, LLMCallLog]
    )
    print("--- Konekcija USPEŠNA! ---")