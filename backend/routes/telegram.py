
from controllers.telegram_controller import (
    add_groups,
    get_groups,
    get_messages,
    process_pending_jobs,
    run_job_workflow,
    sync_all_messages,
    sync_messages,
    telegram_login,
)
from database import get_db
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from schemas.response import ApiResponse
from schemas.telegram import AddGroup
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.post("/login")
async def login(
    code: str |None = Query(default=None),
    password: str |None = Query(default=None),
):
    return await telegram_login(code, password)


@router.get("/channels")
async def groups():
    return await get_groups()

@router.post("/channels", response_model=ApiResponse)
async def add_groups_route(
    data: list[AddGroup],
    db: AsyncSession = Depends(get_db),
):
    return await add_groups(data, db)


@router.post("/channels/{channel_id}/messages/sync", response_model=ApiResponse)
async def sync_channel_messages(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await sync_messages(channel_id, db)


@router.post("/messages/sync", response_model=ApiResponse)
async def sync_all_channel_messages(
    db: AsyncSession = Depends(get_db),
):
    return await sync_all_messages(db)


@router.post("/jobs/process", response_model=ApiResponse)
async def process_jobs(
    db: AsyncSession = Depends(get_db),
):
    return await process_pending_jobs(db)


@router.post("/jobs/run")
async def run_jobs(
    db: AsyncSession = Depends(get_db),
):
    return StreamingResponse(
        run_job_workflow(db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/messages/{group_id}")
async def messages(
    group_id: int,
    limit: int = Query(default=20, ge=1, le=100),
):
    return await get_messages(group_id, limit)
