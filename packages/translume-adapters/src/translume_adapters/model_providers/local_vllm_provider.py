from __future__ import annotations

from translume_clients.local_vllm import LocalVLLMClient


class LocalVLLMProvider:
    """Model provider that routes structured outputs to local vLLM."""

    def __init__(self, client: LocalVLLMClient) -> None:
        self._client = client

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        request = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        }
        return await self._client.structured_completion(request)
