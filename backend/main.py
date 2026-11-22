from contextlib import asynccontextmanager

from database import close_db, init_db
from exceptions.handlers import (
    AppError,
    app_error_handler,
    validation_error_handler,
)
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from routes.telegram import router as telegram_router
from services.telegram_service import telegram_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        await telegram_service.connect()
        yield
    finally:
        try:
            await telegram_service.disconnect()
        finally:
            await close_db()


app = FastAPI(
    title="Telegram Job Aggregator",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

@app.get("/")
async def home():
    return {
        "status": "running",
        "application": "Telegram Job Aggregator",
    }


app.include_router(telegram_router)
