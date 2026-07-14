from __future__ import annotations

from translume_clients.local_vllm import LocalVLLMClient


class LocalVLLMProvider:
    """Route bounded structured outputs to local vLLM.

    Acceptance criteria:
        1. Every structured request includes a positive output-token bound.
        2. Report extraction uses its dedicated positive output-token bound.
        3. Request construction does not mutate caller-owned values.
    """

    def __init__(
        self,
        client: LocalVLLMClient,
        *,
        structured_output_max_tokens: int = 3000,
        report_extraction_max_tokens: int = 2500,
    ) -> None:
        if structured_output_max_tokens <= 0:
            raise ValueError("structured_output_max_tokens must be positive")
        if report_extraction_max_tokens <= 0:
            raise ValueError("report_extraction_max_tokens must be positive")
        self._client = client
        self._structured_output_max_tokens = structured_output_max_tokens
        self._report_extraction_max_tokens = report_extraction_max_tokens

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
            "max_tokens": self._max_tokens_for_schema(schema_name),
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

    def _max_tokens_for_schema(self, schema_name: str) -> int:
        if schema_name == "ReportExtractionOutput":
            return self._report_extraction_max_tokens
        return self._structured_output_max_tokens
