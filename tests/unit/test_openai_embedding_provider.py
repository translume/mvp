from __future__ import annotations

import json
import math

import httpx
import pytest
from translume_adapters.embedding_providers.openai_embedding_provider import (
    OpenAISyncEmbeddingProvider,
    embedding_batches,
    validate_embedding_response,
)
from translume_clients.openai_client import OpenAISyncClient
from translume_schemas.model_calls import ModelResponseError


def test_remote_embedding_batches_are_deduplicated_cached_and_reordered():
    batches = []

    def handle(request):
        payload = json.loads(request.content)
        batches.append(payload)
        rows = [
            {"index": index, "embedding": [float(len(text)), 1.0, 2.0]}
            for index, text in enumerate(payload["input"])
        ]
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-large",
                "data": list(reversed(rows)),
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = OpenAISyncClient("test-key", http_client=http)
        provider = OpenAISyncEmbeddingProvider(client, dimensions=3, batch_size=2)
        first = provider.embed(["gene", "long passage", "gene"])
        second = provider.embed(["long passage", "gene"])
    assert len(batches) == 1
    assert batches[0]["input"] == ["gene", "long passage"]
    assert batches[0]["dimensions"] == 3
    assert first == [[4.0, 1.0, 2.0], [12.0, 1.0, 2.0], [4.0, 1.0, 2.0]]
    assert second == [first[1], first[0]]
    first[0][0] = 999
    assert second[1][0] == 4.0
    assert client.call_records[0].endpoint == "/embeddings"
    assert client.call_records[0].input_tokens == 5


@pytest.mark.parametrize(
    "rows",
    [
        [{"index": 0, "embedding": [1.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}],
        [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [3.0, 4.0]}],
        [
            {"index": 0, "embedding": [math.nan, 2.0]},
            {"index": 1, "embedding": [3.0, 4.0]},
        ],
        [{"index": 0, "embedding": [0.0, 0.0]}, {"index": 1, "embedding": [3.0, 4.0]}],
        [{"index": 0, "embedding": [True, 2.0]}, {"index": 1, "embedding": [3.0, 4.0]}],
        [{"index": 0, "embedding": [1.0, 2.0]}],
    ],
)
def test_invalid_embeddings_are_never_filled_or_used(rows):
    with pytest.raises(ModelResponseError):
        validate_embedding_response({"data": rows}, expected_count=2, dimensions=2)


def test_conservative_token_bounds_cover_utf8_and_total_batch_limits():
    with pytest.raises(ValueError, match="nonempty"):
        embedding_batches([" "], 32)
    with pytest.raises(ValueError, match="8192-byte"):
        embedding_batches(["é" * 4097], 32)
    batches = embedding_batches(["x" * 8192] * 100, 2048)
    assert sum(map(len, batches)) == 100
    assert all(sum(len(text.encode()) for text in batch) <= 300000 for batch in batches)
    assert embedding_batches([], 32) == []
    with pytest.raises(TypeError):
        embedding_batches("text is not a list", 32)
