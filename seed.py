import asyncio
from app.core.database import AsyncSessionLocal, Base, engine
from app.api.v1.endpoints.slots import seed_demo_data

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        result = await seed_demo_data(db=session)
        print("Seed result:", result)

if __name__ == "__main__":
    asyncio.run(init_db())