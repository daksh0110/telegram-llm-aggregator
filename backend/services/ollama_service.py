import json
from typing import Any

import httpx

from config import settings


class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

        if not settings.llm_prompt_path.is_file():
            raise RuntimeError(
                f"Ollama prompt file not found: {settings.llm_prompt_path}"
            )

        self.prompt = settings.llm_prompt_path.read_text(encoding="utf-8")

    async def filter_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[tuple[int, int], dict[str, Any]]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=10.0)
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"messages": messages},
                                ensure_ascii=False,
                                default=str,
                            ),
                        },
                    ],
                    "stream": False,
                    "format": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "channel_id": {"type": "integer"},
                                        "message_id": {"type": "integer"},
                                        "is_relevant": {"type": "boolean"},
                                    },
                                    "required": [
                                        "channel_id",
                                        "message_id",
                                        "is_relevant",
                                    ],
                                },
                            }
                        },
                        "required": ["results"],
                    },
                    "options": {"temperature": 0},
                },
            )

        if not response.is_success:
            try:
                error_payload = response.json()
            except (TypeError, ValueError):
                error_payload = {}

            error_detail = (
                error_payload.get("error")
                if isinstance(error_payload, dict)
                else None
            ) or response.text.strip()

            if not error_detail:
                error_detail = "Ollama did not provide an error message"

            raise RuntimeError(
                f"Ollama returned HTTP {response.status_code}: "
                f"{str(error_detail)[:1000]}"
            )

        try:
            content = response.json()["message"]["content"]
            result = json.loads(content)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Ollama returned invalid JSON") from error

        if isinstance(result, list):
            result = {"results": result}
        elif (
            isinstance(result, dict)
            and "results" not in result
            and "channel_id" in result
            and "message_id" in result
        ):
            result = {"results": [result]}

        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            if isinstance(result, dict):
                shape = f"object with keys: {', '.join(sorted(result.keys()))}"
            else:
                shape = type(result).__name__
            raise RuntimeError(
                f"Ollama response must contain a results array; got {shape}"
            )

        filtered = {}
        expected = {
            (int(message["channel_id"]), int(message["message_id"]))
            for message in messages
        }

        for item in result["results"]:
            if not isinstance(item, dict):
                raise RuntimeError("Each Ollama result must be a JSON object")

            try:
                key = (int(item["channel_id"]), int(item["message_id"]))
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    "Ollama results must include channel_id and message_id"
                ) from error

            if key not in expected:
                raise RuntimeError("Ollama returned a result for an unknown message")
            if key in filtered:
                raise RuntimeError("Ollama returned a duplicate message result")

            is_relevant = item.get("is_relevant")
            if not isinstance(is_relevant, bool):
                is_relevant = item.get("decision") == "RELEVANT"

            filtered[key] = {
                **item,
                "is_relevant": is_relevant,
            }

        for key in expected - filtered.keys():
            filtered[key] = {
                "channel_id": key[0],
                "message_id": key[1],
                "is_relevant": False,
                "decision": "REJECTED",
                "duplicate": False,
            }

        return filtered


ollama_service = OllamaService()
