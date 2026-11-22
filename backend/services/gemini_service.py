import json
from typing import Any

from google import genai
from google.genai import types

from config import settings


class GeminiService:
    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Add it to backend/.env."
            )

        if not settings.llm_prompt_path.is_file():
            raise RuntimeError(
                f"Gemini prompt file not found: {settings.llm_prompt_path}"
            )

        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.prompt = settings.llm_prompt_path.read_text(encoding="utf-8")

    async def filter_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[tuple[int, int], dict[str, Any]]:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=json.dumps(
                {"messages": messages},
                ensure_ascii=False,
                default=str,
            ),
            config=types.GenerateContentConfig(
                system_instruction=self.prompt,
                response_mime_type="application/json",
                temperature=0,
            ),
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response")

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as error:
            raise RuntimeError("Gemini returned invalid JSON") from error

        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise RuntimeError("Gemini response must contain a results array")

        filtered = {}
        for item in result["results"]:
            if not isinstance(item, dict):
                raise RuntimeError("Each Gemini result must be a JSON object")

            try:
                key = (int(item["channel_id"]), int(item["message_id"]))
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    "Gemini results must include channel_id and message_id"
                ) from error

            if not isinstance(item.get("is_relevant"), bool):
                raise RuntimeError("Each Gemini result must include is_relevant")
            if key in filtered:
                raise RuntimeError("Gemini returned a duplicate message result")

            filtered[key] = item

        expected = {
            (int(message["channel_id"]), int(message["message_id"]))
            for message in messages
        }
        if filtered.keys() != expected:
            raise RuntimeError("Gemini did not return a result for every message")

        return filtered


gemini_service = GeminiService()
