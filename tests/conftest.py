import pytest_asyncio
from data.db import init_db


@pytest_asyncio.fixture(autouse=True, scope="session")
async def init_beanie():
    await init_db()
