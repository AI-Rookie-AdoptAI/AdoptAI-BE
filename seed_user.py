"""Create a test user for development."""

import asyncio

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = User(email="test@example.com", name="테스트 유저", hashed_password=hash_password("password123"))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created user: {user.email} (id: {user.id})")


if __name__ == "__main__":
    asyncio.run(main())
