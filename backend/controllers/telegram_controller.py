
import json

from fastapi import HTTPException
from modals.telegram_channel import TelegramChannel
from schemas.response import error_response, success_response
from schemas.telegram import AddGroup
from services.job_workflow_service import job_workflow_service
from services.telegram_service import telegram_service
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError, RPCError


async def telegram_login(
    code: str |None = None,
    password: str |None = None,
):
    try:
        return await telegram_service.login(code, password)
    except FloodWaitError as error:
        raise HTTPException(
            status_code=429,
            detail=f"Telegram asks you to wait {error.seconds} seconds.",
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


async def get_groups():
    if not await telegram_service.is_user_authorized():
        raise HTTPException(status_code=401, detail="Login to Telegram first")

    return await telegram_service.get_groups()


async def add_groups(data: list[AddGroup], db: AsyncSession):
    if not await telegram_service.is_user_authorized():
        return error_response(
            message="Login to Telegram first",
            error="Telegram user is not authorized",
        )

    saved_groups = []

    for group in data:
        try:
            details = await telegram_service.get_group_details(group.channel_id)
        except FloodWaitError as error:
            return error_response(
                message="Telegram rate limit reached",
                error=f"Wait {error.seconds} seconds",
            )
        except (ValueError, RPCError) as error:
            return error_response(
                message="Could not find this Telegram group",
                error=str(error),
            )

        try:
            existing_group = await db.scalar(
                select(TelegramChannel).where(
                    TelegramChannel.channel_id == group.channel_id
                )
            )
        except SQLAlchemyError as error:
            await db.rollback()
            return error_response(
                message="Could not read groups from the database",
                error=str(error),
            )

        if existing_group:
            saved_groups.append(existing_group)
            continue

        new_group = TelegramChannel(**details)
        db.add(new_group)
        saved_groups.append(new_group)

    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        return error_response(
            message="Could not save groups",
            error=str(error),
        )

    return success_response(
        data=[
            {
                "id": group.id,
                "channel_id": group.channel_id,
                "channel_name": group.channel_name,
            }
            for group in saved_groups
        ],
        message="Groups saved successfully",
    )


async def get_messages(group_id: int, limit: int):
    if not await telegram_service.is_user_authorized():
        raise HTTPException(status_code=401, detail="Login to Telegram first")

    try:
        return await telegram_service.get_messages(group_id, limit)
    except FloodWaitError as error:
        raise HTTPException(
            status_code=429,
            detail=f"Wait {error.seconds} seconds",
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


async def sync_messages(channel_id: int, db: AsyncSession):
    if not await telegram_service.is_user_authorized():
        return error_response(
            message="Login to Telegram first",
            error="Telegram user is not authorized",
        )

    try:
        result = await telegram_service.fetch_new_messages(channel_id, db)
    except FloodWaitError as error:
        await db.rollback()
        return error_response(
            message="Telegram rate limit reached",
            error=f"Wait {error.seconds} seconds",
        )
    except (ValueError, RPCError, SQLAlchemyError) as error:
        await db.rollback()
        return error_response(
            message="Could not fetch new messages",
            error=str(error),
        )

    return success_response(
        data=result,
        message="New messages saved successfully",
    )


async def sync_all_messages(db: AsyncSession):
    if not await telegram_service.is_user_authorized():
        return error_response(
            message="Login to Telegram first",
            error="Telegram user is not authorized",
        )

    try:
        result = await telegram_service.fetch_all_new_messages(db)
    except FloodWaitError as error:
        await db.rollback()
        return error_response(
            message="Telegram rate limit reached",
            error=f"Wait {error.seconds} seconds",
        )
    except (ValueError, RPCError, SQLAlchemyError) as error:
        await db.rollback()
        return error_response(
            message="Could not fetch messages",
            error=str(error),
        )

    return success_response(
        data=result,
        message="All new messages saved successfully",
    )


async def process_pending_jobs(db: AsyncSession):
    try:
        result = await job_workflow_service.process_pending_messages(db)
    except (RuntimeError, SQLAlchemyError) as error:
        await db.rollback()
        return error_response(
            message="Could not process pending messages",
            error=str(error),
        )

    return success_response(
        data=result,
        message="Pending messages processed successfully",
    )


async def run_job_workflow(db: AsyncSession):
    if not await telegram_service.is_user_authorized():
        yield f"data: {json.dumps({'stage': 'workflow', 'status': 'error', 'error': 'Login to Telegram first'})}\n\n"
        return

    try:
        async for event in telegram_service.stream_new_messages_for_all_channels(db):
            yield f"data: {json.dumps(event)}\n\n"

        async for event in job_workflow_service.stream_pending_messages(db):
            yield f"data: {json.dumps(event)}\n\n"
            if event["status"] == "stopped":
                return
    except (RuntimeError, SQLAlchemyError) as error:
        await db.rollback()
        yield (
            "data: "
            + json.dumps(
                {
                    "stage": "workflow",
                    "status": "error",
                    "error": str(error),
                }
            )
            + "\n\n"
        )
        return

    yield 'data: {"stage":"workflow","status":"completed"}\n\n'
