
import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def main():

    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        print(response.json())


asyncio.run(main())
