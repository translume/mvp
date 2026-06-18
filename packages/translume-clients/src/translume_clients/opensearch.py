from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class OpenSearchClientError(RuntimeError):
    """Raised when OpenSearch returns an unexpected response."""


@dataclass(frozen=True)
class OpenSearchClientConfig:
    """Connection configuration for OpenSearch.

    Attributes:
        base_url: OpenSearch HTTP endpoint.
        timeout_seconds: HTTP timeout in seconds.
    """

    base_url: str = "http://opensearch:9200"
    timeout_seconds: float = 30.0


class OpenSearchVectorStore:
    """HTTP OpenSearch retrieval/document store client.

    Acceptance criteria:
        1. Network I/O is isolated to this boundary class.
        2. Index creation uses real OpenSearch HTTP endpoints.
        3. Bulk indexing uses the `_bulk` endpoint.
        4. Search uses the `_search` endpoint.
        5. Non-success responses raise `OpenSearchClientError`.
        6. The current MVP uses lexical/metadata queries only; this client
           does not imply vector/HNSW retrieval is active.
    """

    def __init__(self, config: OpenSearchClientConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    async def ensure_index(self, index_name: str, body: dict[str, Any]) -> None:
        """Create an index if it does not already exist.

        Acceptance criteria:
            1. Performs HEAD before PUT.
            2. Existing indexes are accepted without mutation.
            3. Creation failures raise `OpenSearchClientError`.

        Args:
            index_name: Name of the OpenSearch index.
            body: OpenSearch index settings and mappings.

        Raises:
            OpenSearchClientError: If OpenSearch rejects the request.
        """
        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            head = await client.head(f"{self._base_url}/{index_name}")
            if head.status_code == 200:
                return
            if head.status_code not in {404}:
                raise OpenSearchClientError(
                    f"index existence check failed for {index_name}: "
                    f"{head.status_code} {head.text}"
                )
            created = await client.put(f"{self._base_url}/{index_name}", json=body)
            if created.status_code not in {200, 201}:
                raise OpenSearchClientError(
                    f"index creation failed for {index_name}: "
                    f"{created.status_code} {created.text}"
                )

    async def index(self, index_name: str, documents: list[dict[str, object]]) -> None:
        """Bulk index documents into OpenSearch.

        Acceptance criteria:
            1. Empty document lists are no-ops.
            2. Every document must include `document_id`.
            3. Bulk API item failures raise `OpenSearchClientError`.
            4. Caller-owned documents are not mutated.

        Args:
            index_name: Target OpenSearch index.
            documents: JSON-compatible documents with `document_id`.

        Raises:
            ValueError: If a document lacks `document_id`.
            OpenSearchClientError: If indexing fails.
        """
        if not documents:
            return
        lines: list[str] = []
        for document in documents:
            document_id = document.get("document_id")
            if not isinstance(document_id, str) or not document_id:
                raise ValueError("every OpenSearch document must include document_id")
            action = {"index": {"_index": index_name, "_id": document_id}}
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(dict(document), separators=(",", ":"), default=str))
        payload = "\n".join(lines) + "\n"
        headers = {"Content-Type": "application/x-ndjson"}
        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/_bulk",
                content=payload,
                headers=headers,
            )
        if response.status_code not in {200, 201}:
            raise OpenSearchClientError(
                f"bulk index failed for {index_name}: "
                f"{response.status_code} {response.text}"
            )
        data = response.json()
        if data.get("errors") is True:
            failures = [
                item
                for item in data.get("items", [])
                if item.get("index", {}).get("error") is not None
            ]
            raise OpenSearchClientError(
                f"bulk index had {len(failures)} failed item(s) for {index_name}"
            )

    async def search(
        self,
        index_name: str,
        query: dict[str, object],
    ) -> list[dict[str, object]]:
        """Search OpenSearch and return hit sources with scores.

        Acceptance criteria:
            1. Uses OpenSearch `_search` endpoint.
            2. Missing hit sources return empty dictionaries with score metadata.
            3. Non-success responses raise `OpenSearchClientError`.

        Args:
            index_name: Index to query.
            query: OpenSearch query body.

        Returns:
            Hit source dictionaries augmented with `_score` and `_id`.
        """
        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/{index_name}/_search",
                json=query,
            )
        if response.status_code != 200:
            raise OpenSearchClientError(
                f"search failed for {index_name}: "
                f"{response.status_code} {response.text}"
            )
        hits = response.json().get("hits", {}).get("hits", [])
        results: list[dict[str, object]] = []
        for hit in hits:
            source = dict(hit.get("_source", {}))
            source["_score"] = hit.get("_score")
            source["_id"] = hit.get("_id")
            results.append(source)
        return results
