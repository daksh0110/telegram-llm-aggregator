import os
from typing import Any

from config import settings
from httpx import HTTPError
from modals.telegram_message import TelegramMessage
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from services.telegram_bot import send_message

if settings.llm_provider == "gemini":
    from services.gemini_service import gemini_service as llm_service
else:
    from services.ollama_service import ollama_service as llm_service


class JobWorkflowService:
    async def process_pending_messages(self, db: AsyncSession) -> dict[str, Any]:
        summary = None
        async for event in self.stream_pending_messages(db):
            if event["status"] == "completed":
                summary = {
                    "total_pending": event["total_messages"],
                    "processed": event["processed"],
                    "sent": event["sent"],
                    "errors": event["errors"],
                }

        if summary is None:
            raise RuntimeError("Message processing ended without a summary")
        return summary

    async def stream_pending_messages(self, db: AsyncSession):
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            raise RuntimeError(
                "TELEGRAM_CHAT_ID is missing. Add your Telegram chat ID to backend/.env."
            )

        messages = (
            await db.execute(
                select(
                    TelegramMessage.id,
                    TelegramMessage.channel_id,
                    TelegramMessage.message_id,
                    TelegramMessage.message_date,
                    TelegramMessage.message_text,
                )
                .where(TelegramMessage.processing_status == "pending")
                .order_by(
                    TelegramMessage.channel_id,
                    TelegramMessage.message_id,
                )
            )
        ).mappings().all()

        total = len(messages)
        processed = 0
        sent = 0
        errors = []
        channels = set()

        yield {
            "stage": "processing",
            "status": "started",
            "total_messages": total,
        }

        for batch_start in range(0, total, settings.llm_batch_size):
            batch = messages[
                batch_start:batch_start + settings.llm_batch_size
            ]
            batch_number = batch_start // settings.llm_batch_size + 1
            yield {
                "stage": "processing",
                "status": "batch_started",
                "batch": batch_number,
                "batch_size": len(batch),
                "current": batch_start + 1,
                "total": total,
            }

            try:
                results = await llm_service.filter_messages(
                    [
                        {
                            "message_id": message["message_id"],
                            "channel_id": message["channel_id"],
                            "date": message["message_date"],
                            "text": message["message_text"],
                        }
                        for message in batch
                    ]
                )
            except (HTTPError, SQLAlchemyError, RuntimeError, ValueError) as error:
                await db.rollback()
                for offset, message in enumerate(batch):
                    error_result = {
                        "channel_id": message["channel_id"],
                        "message_id": message["message_id"],
                        "error": str(error),
                    }
                    errors.append(error_result)
                    yield {
                        "stage": "processing",
                        "status": "message_error",
                        "current": batch_start + offset + 1,
                        "total": total,
                        **error_result,
                    }
                yield {
                    "stage": "processing",
                    "status": "stopped",
                    "current": batch_start + 1,
                    "total": total,
                    "error": str(error),
                }
                return

            for offset, message in enumerate(batch):
                channels.add(message["channel_id"])
                index = batch_start + offset + 1
                result = results[
                    (int(message["channel_id"]), int(message["message_id"]))
                ]
                operation = "send_to_bot" if result["is_relevant"] else "save_status"

                try:
                    if result["is_relevant"]:
                        await send_message(
                            int(chat_id),
                            message["message_text"] or "",
                        )
                        sent += 1

                    operation = "save_status"
                    await db.execute(
                        update(TelegramMessage)
                        .where(TelegramMessage.id == message["id"])
                        .values(processing_status="processed")
                    )
                    await db.commit()
                    processed += 1
                    yield {
                        "stage": "processing",
                        "status": "message_completed",
                        "current": index,
                        "total": total,
                        "processed": processed,
                        "sent": sent,
                        "channel_id": message["channel_id"],
                        "message_id": message["message_id"],
                    }
                except (HTTPError, SQLAlchemyError, RuntimeError, ValueError) as error:
                    await db.rollback()
                    if isinstance(error, HTTPError):
                        error_message = (
                            f"Telegram bot request failed ({type(error).__name__})"
                        )
                    else:
                        error_message = str(error).strip() or (
                            f"{type(error).__name__} raised without an error message"
                        )
                    error_result = {
                        "channel_id": message["channel_id"],
                        "message_id": message["message_id"],
                        "operation": operation,
                        "error_type": type(error).__name__,
                        "error": error_message,
                    }
                    errors.append(error_result)
                    yield {
                        "stage": "processing",
                        "status": "message_error",
                        "current": index,
                        "total": total,
                        **error_result,
                    }

            yield {
                "stage": "processing",
                "status": "batch_completed",
                "batch": batch_number,
                "current": batch_start + len(batch),
                "total": total,
                "processed": processed,
                "sent": sent,
            }

        for channel_id in channels:
            latest_message_id = await db.scalar(
                select(func.max(TelegramMessage.message_id)).where(
                    TelegramMessage.channel_id == channel_id
                )
            )

            if latest_message_id is not None:
                await db.execute(
                    delete(TelegramMessage).where(
                        TelegramMessage.channel_id == channel_id,
                        TelegramMessage.message_id < latest_message_id,
                        TelegramMessage.processing_status == "processed",
                    )
                )

        await db.commit()
        yield {
            "stage": "processing",
            "status": "completed",
            "total_messages": total,
            "processed": processed,
            "sent": sent,
            "errors": errors,
        }


job_workflow_service = JobWorkflowService()
