import os

from dotenv import load_dotenv
from modals.telegram_channel import TelegramChannel
from modals.telegram_message import TelegramMessage
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError

load_dotenv()


class TelegramService:
    def __init__(self):
        api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        try:
            self.api_id = int(api_id) if api_id else 0
        except ValueError as error:
            raise RuntimeError("TELEGRAM_API_ID must be a number.") from error
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.phone = os.getenv("TELEGRAM_PHONE", "")
        self._client: TelegramClient | None = None

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            raise RuntimeError("Telegram client is not connected.")
        return self._client

    async def connect(self):
        if not self.api_id or not self.api_hash:
            raise RuntimeError("Telegram API credentials missing in .env")

        self._client = TelegramClient(
            "telegram_session",
            self.api_id,
            self.api_hash,
        )
        await self._client.connect()

    async def disconnect(self):
        if self._client is not None:
            await self._client.disconnect()

    async def is_user_authorized(self) -> bool:
        return await self.client.is_user_authorized()

    async def login(
        self,
        code: str |None = None,
        password: str |None = None,
    ):
        if await self.client.is_user_authorized():
            return {"status": "already_authenticated"}

        if not code:
            await self.client.send_code_request(self.phone)
            return {
                "status": "code_sent",
                "message": "Check your Telegram app for the login code.",
            }

        try:
            await self.client.sign_in(self.phone, code)
        except SessionPasswordNeededError:
            if not password:
                return {
                    "status": "password_required",
                    "message": "Two-step verification is enabled.",
                }

            await self.client.sign_in(password=password)

        return {"status": "authenticated"}

    async def get_groups(self):
        dialogs = []

        async for dialog in self.client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                dialogs.append(
                    {
                        "id": dialog.id,
                        "name": dialog.name,
                        "type": "group" if dialog.is_group else "channel",
                    }
                )

        return dialogs

    async def get_group_details(self, channel_id: int) -> dict[str, int | str]:
        entity = await self.client.get_entity(channel_id)
        channel_name = getattr(entity, "title", None)

        if not channel_name:
            raise ValueError(f"Telegram ID {channel_id} is not a group or channel")

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
        }

    async def get_messages(self, group_id: int, limit: int):
        entity = await self.client.get_entity(group_id)
        messages = []

        async for message in self.client.iter_messages(entity, limit=limit):
            if not message.text:
                continue

            messages.append(
                {
                    "message_id": message.id,
                    "date": message.date.isoformat(),
                    "text": message.text,
                }
            )

        return {
            "group_id": group_id,
            "total": len(messages),
            "messages": messages,
        }
    
    async def get_unread_count(self, channel_id: int):
        dialogs = await self.client.get_dialogs()

        for dialog in dialogs:
            if dialog.id == channel_id:
                return {
                    "channel_id": channel_id,
                    "unread_count": dialog.unread_count,
                }

        return {
            "channel_id": channel_id,
            "unread_count": 0,
        }

    async def fetch_new_messages(
        self,
        channel_id: int,
        db: AsyncSession,
    ):
        last_message_id = await db.scalar(
            select(func.max(TelegramMessage.message_id)).where(
                TelegramMessage.channel_id == channel_id
            )
        ) or 0

        entity = await self.client.get_entity(channel_id)
        new_messages = []

        async for message in self.client.iter_messages(
            entity,
            min_id=last_message_id,
            limit=100 if last_message_id == 0 else None,
        ):
            if not message.text:
                continue

            new_messages.append(
                TelegramMessage(
                    channel_id=channel_id,
                    message_id=message.id,
                    message_text=message.text,
                    message_date=message.date,
                )
            )

        db.add_all(new_messages)
        await db.commit()

        return {
            "channel_id": channel_id,
            "new_messages": len(new_messages),
        }

    async def fetch_all_new_messages(self, db: AsyncSession):
        channel_ids = (
            await db.scalars(select(TelegramChannel.channel_id))
        ).all()
        results = []

        for channel_id in channel_ids:
            try:
                result = await self.fetch_new_messages(channel_id, db)
            except FloodWaitError as error:
                await db.rollback()
                result = {
                    "channel_id": channel_id,
                    "new_messages": 0,
                    "error": f"Wait {error.seconds} seconds",
                }
            except (ValueError, RPCError, SQLAlchemyError) as error:
                await db.rollback()
                result = {
                    "channel_id": channel_id,
                    "new_messages": 0,
                    "error": str(error),
                }

            results.append(result)

        return {
            "total_new_messages": sum(
                result["new_messages"] for result in results
            ),
            "channels": results,
        }

    async def stream_new_messages_for_all_channels(self, db: AsyncSession):
        channel_ids = (
            await db.scalars(select(TelegramChannel.channel_id))
        ).all()
        total_new_messages = 0

        yield {
            "stage": "sync",
            "status": "started",
            "total_channels": len(channel_ids),
        }

        for index, channel_id in enumerate(channel_ids, start=1):
            yield {
                "stage": "sync",
                "status": "channel_started",
                "channel_id": channel_id,
                "current": index,
                "total": len(channel_ids),
            }

            try:
                result = await self.fetch_new_messages(channel_id, db)
            except FloodWaitError as error:
                await db.rollback()
                result = {
                    "channel_id": channel_id,
                    "new_messages": 0,
                    "error": f"Wait {error.seconds} seconds",
                }
            except (ValueError, RPCError, SQLAlchemyError) as error:
                await db.rollback()
                result = {
                    "channel_id": channel_id,
                    "new_messages": 0,
                    "error": str(error),
                }

            total_new_messages += result["new_messages"]
            yield {
                "stage": "sync",
                "status": "channel_completed",
                **result,
                "current": index,
                "total": len(channel_ids),
            }

        yield {
            "stage": "sync",
            "status": "completed",
            "total_new_messages": total_new_messages,
            "total_channels": len(channel_ids),
        }


telegram_service = TelegramService()
