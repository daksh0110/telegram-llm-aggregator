
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def send_message(chat_id: int, text: str):
    text = text.replace("**", "")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text
            }
        )

        response.raise_for_status()
        return response.json()
