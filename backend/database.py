import os
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv(Path(__file__).resolve().parent / ".env")

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is missing. Set it in backend/.env using the "
        "postgresql+asyncpg://user:password@host:port/database format."
    )

if not database_url.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        "DATABASE_URL must use the postgresql+asyncpg:// scheme."
    )

engine = create_async_engine(database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from modals.telegram_channel import TelegramChannel
    from modals.telegram_message import TelegramMessage
    async with engine.begin() as connection:
        await connection.run_sync(TelegramChannel.metadata.create_all)
        await connection.run_sync(TelegramMessage.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()
