import os
from beanie import init_beanie
from pymongo import AsyncMongoClient
from dotenv import load_dotenv
from data.schemas import VisionDoc, FeatureLogItem, SessionEntry

load_dotenv()

async def init_db():
    mongo_uri = os.getenv("MONGODB_URI")
    client = AsyncMongoClient(mongo_uri)
    
    await init_beanie(
        database=client.vibeguard,
        document_models=[VisionDoc, FeatureLogItem, SessionEntry]
    )
    print("--- Konekcija USPEŠNA! ---")