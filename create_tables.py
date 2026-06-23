"""Run this once to create all database tables."""

import asyncio

from app.core.database import Base, engine

# Import all models so Base.metadata knows about them
import app.models.user  # noqa: F401
import app.models.refresh_token  # noqa: F401
import app.models.announcement  # noqa: F401
import app.models.chat  # noqa: F401


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("All tables created successfully.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
