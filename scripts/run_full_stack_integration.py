#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATHS = (
    ROOT,
    ROOT / "packages" / "translume-schemas" / "src",
    ROOT / "packages" / "translume-ports" / "src",
    ROOT / "packages" / "translume-core" / "src",
    ROOT / "packages" / "translume-clients" / "src",
    ROOT / "packages" / "translume-adapters" / "src",
)
for package_path in PACKAGE_PATHS:
    value = str(package_path)
    if value not in sys.path:
        sys.path.insert(0, value)

from scripts.full_stack_preflight import (
    DEFAULT_REQUIREMENTS,
    PreflightError,
    env_value,
    load_requirements,
    run_preflight,
)
from translume_clients.opensearch import OpenSearchClientConfig, OpenSearchVectorStore
from translume_clients.postgres import PostgresClientConfig, PostgresLedgerStore
from translume_core.indexing.persistence import ensure_mvp_indexes
from translume_core.indexing.retrieval_scope import require_lexical_retrieval_scope



class FullStackIntegrationError(RuntimeError):
    """Raised when the real full-stack integration check fails."""


@dataclass(frozen=True)
class ServiceEndpoint:
    """HTTP service endpoint loaded from integration requirements.

    Attributes:
        name: Service name.
        url: Service base URL.
        path: Health path.
        required_fields: Required JSON fields and values.
    """

    name: str
    url: str
    path: str
    required_fields: Mapping[str, object]


@dataclass(frozen=True)
class FullStackIntegrationResult:
    """Summary returned by the full-stack integration runner.

    Attributes:
        case_id: Review packet case identifier.
        session_id: Review packet session identifier.
        claim_id: Claim selected for validation endpoint round trip.
        checked_paths: Review packet paths checked for non-empty values.
    """

    case_id: str
    session_id: str
    claim_id: str
    checked_paths: tuple[str, ...]


WORKFLOW_SET_FIELDS = frozenset(
    {
        "configured_workflows",
        "missing_required_workflows",
    }
)


def health_field_mismatch(
    key: str,
    expected: object,
    payload: Mapping[str, object],
) -> str | None:
    """Return a health-field mismatch message when one exists.

    Acceptance criteria:
        1. Scalar fields must match exactly.
        2. Workflow list fields compare by set because order is not meaningful.
        3. Missing `missing_required_workflows` is equivalent to an empty list
           only when the expected value is an empty list.
        4. The input payload is not mutated.

    Args:
        key: Health response field name.
        expected: Required field value from integration requirements.
        payload: JSON health response object.

    Returns:
        A mismatch message, or `None` when the field satisfies requirements.
    """
    actual = payload.get(key)
    if key == "missing_required_workflows" and actual is None and expected == []:
        actual = []
    if key in WORKFLOW_SET_FIELDS and isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{key} expected {expected!r} got {actual!r}"
        if set(actual) != set(expected):
            return f"{key} expected {expected!r} got {actual!r}"
        return None
    if actual != expected:
        return f"{key} expected {expected!r} got {actual!r}"
    return None


def build_vllm_structured_output_request(
    *,
    model: str,
    schema: Mapping[str, object],
) -> dict[str, object]:
    """Build the vLLM structured-output preflight request.

    Acceptance criteria:
        1. Uses a single `user` message for chat-template compatibility.
        2. Preserves the configured JSON schema response format.
        3. Uses deterministic generation settings.
        4. Does not mutate the supplied schema.

    Args:
        model: Model name served by the local vLLM endpoint.
        schema: JSON schema response-format object from requirements.

    Returns:
        OpenAI-compatible chat completion request payload.
    """
    return {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return only schema-valid JSON for this status check. "
                    "Return status ready for Translume."
                ),
            }
        ],
        "response_format": {"type": "json_schema", "json_schema": dict(schema)},
    }


def get_path(payload: object, path: str) -> object:
    """Return a nested value from dict/list payloads using dotted paths.

    Acceptance criteria:
        1. Supports dictionaries with string keys.
        2. Supports list indexes as decimal path parts.
        3. Missing paths raise `FullStackIntegrationError`.
        4. Input payload is not mutated.

    Args:
        payload: JSON-like object.
        path: Dotted path such as `bundle.claims.0.claim_id`.

    Returns:
        Nested value at `path`.
    """
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise FullStackIntegrationError(f"missing response path: {path}")
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as error:
                raise FullStackIntegrationError(f"missing response path: {path}") from error
        else:
            raise FullStackIntegrationError(f"path is not traversable: {path}")
    return current


def is_non_empty(value: object) -> bool:
    """Return whether a response value is materially non-empty.

    Acceptance criteria:
        1. Blank strings are empty.
        2. Empty containers are empty.
        3. None is empty.
        4. Numbers and booleans are non-empty values.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def assert_non_empty_paths(payload: object, paths: Sequence[str]) -> tuple[str, ...]:
    """Assert configured response paths are present and non-empty.

    Acceptance criteria:
        1. Every configured path must exist.
        2. Every configured path must contain a non-empty value.
        3. All failures are reported together.
        4. Function is deterministic and pure.
    """
    failures: list[str] = []
    for path in paths:
        try:
            value = get_path(payload, path)
        except FullStackIntegrationError as error:
            failures.append(str(error))
            continue
        if not is_non_empty(value):
            failures.append(f"empty response path: {path}")
    if failures:
        raise FullStackIntegrationError("; ".join(failures))
    return tuple(paths)


def assert_absent_phrases(payload: object, phrases: Sequence[str]) -> None:
    """Assert prohibited clinical phrases are absent from response JSON.

    Acceptance criteria:
        1. Checks the complete JSON payload serialization.
        2. Matching is case-insensitive.
        3. All found phrases are reported together.
        4. Function is deterministic and pure.
    """
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False).casefold()
    found = [phrase for phrase in phrases if phrase.casefold() in serialized]
    if found:
        raise FullStackIntegrationError(
            "unsafe clinical phrase(s) found in full-stack output: " + ", ".join(found)
        )


def endpoint_from_config(
    config: Mapping[str, object],
    environment: Mapping[str, str],
) -> ServiceEndpoint:
    """Build a service endpoint from requirements JSON.

    Acceptance criteria:
        1. Uses explicit environment override when present.
        2. Falls back to configured local URL.
        3. Required fields must be a mapping.
        4. Function is deterministic and pure.
    """
    url_env = str(config["url_env"])
    required_fields = config.get("required_fields", {})
    if not isinstance(required_fields, dict):
        raise ValueError("service required_fields must be an object")
    return ServiceEndpoint(
        name=str(config["name"]),
        url=env_value(url_env, environment) or str(config["default_url"]),
        path=str(config["path"]),
        required_fields=required_fields,
    )


async def wait_for_json_endpoint(
    endpoint: ServiceEndpoint,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, object]:
    """Wait for a real HTTP JSON service endpoint.

    Acceptance criteria:
        1. Repeatedly calls the configured service endpoint.
        2. Requires HTTP 2xx.
        3. Requires JSON object response.
        4. Requires configured fields to match with field-appropriate
           comparison semantics.
        5. Times out with the last observed error.
    """
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    url = endpoint.url.rstrip("/") + endpoint.path
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
            if response.status_code >= 400:
                last_error = f"{response.status_code} {response.text}"
            else:
                payload = response.json()
                if not isinstance(payload, dict):
                    last_error = "health response was not a JSON object"
                else:
                    mismatches = [
                        mismatch
                        for key, expected in endpoint.required_fields.items()
                        if (
                            mismatch := health_field_mismatch(
                                key,
                                expected,
                                payload,
                            )
                        )
                        is not None
                    ]
                    if not mismatches:
                        return payload
                    last_error = "; ".join(mismatches)
        except Exception as error:  # pragma: no cover - integration only.
            last_error = str(error)
        await asyncio.sleep(interval_seconds)
    raise FullStackIntegrationError(
        f"service {endpoint.name} failed health check at {url}: {last_error}"
    )


async def wait_for_all_services(
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    """Wait for all configured HTTP services to become healthy."""
    services = requirements.get("service_health", [])
    if not isinstance(services, list):
        raise ValueError("service_health must be a list")
    for raw_service in services:
        if not isinstance(raw_service, dict):
            raise ValueError("service_health entries must be objects")
        await wait_for_json_endpoint(
            endpoint_from_config(raw_service, environment),
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )


def validate_retrieval_scope(
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
) -> None:
    """Validate live-stack retrieval scope is honest about vector support."""
    config = requirements.get("retrieval_scope", {})
    if not isinstance(config, dict):
        raise ValueError("retrieval_scope requirements must be an object")
    mode_env = str(config.get("mode_env", "TRANSLUME_RETRIEVAL_MODE"))
    mode = env_value(mode_env, environment) or str(config.get("required_mode", "lexical"))
    try:
        require_lexical_retrieval_scope(mode)
    except Exception as error:
        raise FullStackIntegrationError(str(error)) from error


async def validate_opensearch(
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
) -> None:
    """Validate real OpenSearch health and initialize MVP indexes."""
    config = requirements.get("opensearch")
    if not isinstance(config, dict):
        raise ValueError("opensearch requirements must be an object")
    base_url = env_value(str(config["url_env"]), environment) or str(config["default_url"])
    health_path = str(config["health_path"])
    endpoint = ServiceEndpoint(
        name="opensearch",
        url=base_url,
        path=health_path,
        required_fields={},
    )
    await wait_for_json_endpoint(endpoint, timeout_seconds=120, interval_seconds=2)
    retrieval_mode = env_value("TRANSLUME_RETRIEVAL_MODE", environment) or "lexical"
    vector_dimension_raw = env_value("TRANSLUME_VECTOR_DIMENSION", environment)
    vector_dimension = int(vector_dimension_raw) if vector_dimension_raw else None
    store = OpenSearchVectorStore(
        OpenSearchClientConfig(
            base_url=base_url,
            timeout_seconds=float(env_value("OPENSEARCH_TIMEOUT_SECONDS", environment) or "30"),
        )
    )
    await ensure_mvp_indexes(
        store,
        retrieval_mode=retrieval_mode,
        vector_dimension=vector_dimension,
    )
    required_indices = config.get("required_indices", [])
    if not isinstance(required_indices, list):
        raise ValueError("opensearch.required_indices must be a list")
    async with httpx.AsyncClient(timeout=30) as client:
        for index in required_indices:
            response = await client.head(f"{base_url.rstrip('/')}/{index}")
            if response.status_code != 200:
                raise FullStackIntegrationError(f"OpenSearch index missing: {index}")


async def validate_postgres(
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
) -> None:
    """Validate real Postgres connectivity and initialize MVP schema."""
    config = requirements.get("postgres")
    if not isinstance(config, dict):
        raise ValueError("postgres requirements must be an object")
    dsn = env_value(str(config["dsn_env"]), environment) or str(config["default_dsn"])
    store = PostgresLedgerStore(
        PostgresClientConfig(
            dsn=dsn,
            connect_timeout_seconds=float(
                env_value("POSTGRES_CONNECT_TIMEOUT_SECONDS", environment) or "10"
            ),
        )
    )
    await store.ensure_schema()
    required_tables = config.get("required_tables", [])
    if not isinstance(required_tables, list):
        raise ValueError("postgres.required_tables must be a list")
    psycopg, _jsonb = _load_psycopg_for_integration()
    async with await psycopg.AsyncConnection.connect(dsn) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            rows = await cursor.fetchall()
    existing = {row[0] for row in rows}
    missing = sorted(set(str(item) for item in required_tables) - existing)
    if missing:
        raise FullStackIntegrationError(
            "Postgres table(s) missing after schema initialization: " + ", ".join(missing)
        )


async def validate_vllm_structured_output(
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
) -> None:
    """Validate real local vLLM structured-output generation."""
    config = requirements.get("vllm")
    if not isinstance(config, dict):
        raise ValueError("vllm requirements must be an object")
    base_url = env_value(str(config["base_url_env"]), environment) or str(config["default_base_url"])
    model = env_value(str(config["model_env"]), environment)
    schema = config.get("structured_schema")
    if not isinstance(schema, dict):
        raise ValueError("vllm.structured_schema must be an object")
    async with httpx.AsyncClient(timeout=120) as client:
        models_response = await client.get(f"{base_url.rstrip('/')}/models")
        if models_response.status_code >= 400:
            raise FullStackIntegrationError(
                f"vLLM /models failed: {models_response.status_code} {models_response.text}"
            )
        request = build_vllm_structured_output_request(model=model, schema=schema)
        response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=request)
    if response.status_code >= 400:
        raise FullStackIntegrationError(
            f"vLLM structured output failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    parsed = content if isinstance(content, dict) else json.loads(str(content))
    if parsed != {"status": "ready", "service": "translume"}:
        raise FullStackIntegrationError(
            "vLLM structured output returned unexpected payload: " + json.dumps(parsed)
        )


async def process_real_report(
    *,
    api_url: str,
    report_path: Path,
    report_type: str,
    timeout_seconds: float,
) -> dict[str, object]:
    """Upload one real PDF report to the production API workflow."""
    with report_path.open("rb") as file_obj:
        files = {"file": (report_path.name, file_obj, "application/pdf")}
        data = {"report_type": report_type}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/api/v1/reports/process",
                files=files,
                data=data,
            )
    if response.status_code >= 400:
        raise FullStackIntegrationError(
            f"report processing failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise FullStackIntegrationError("report processing did not return a JSON object")
    return payload


async def validate_human_review_roundtrip(
    *,
    api_url: str,
    packet: Mapping[str, object],
) -> str:
    """Validate real claim-card endpoints without marking a claim as clinically validated."""
    session_id = str(packet["session_id"])
    async with httpx.AsyncClient(timeout=60) as client:
        cards_response = await client.get(
            f"{api_url.rstrip('/')}/api/v1/review-packets/{session_id}/validation-cards"
        )
    if cards_response.status_code >= 400:
        raise FullStackIntegrationError(
            f"validation-card fetch failed: {cards_response.status_code} {cards_response.text}"
        )
    cards_payload = cards_response.json()
    claims = cards_payload.get("claims")
    if not isinstance(claims, list) or not claims:
        raise FullStackIntegrationError("no validation cards returned for real packet")
    first_claim = claims[0]
    if not isinstance(first_claim, dict):
        raise FullStackIntegrationError("validation card is not a JSON object")
    claim_id = str(first_claim.get("claim_id", "")).strip()
    if not claim_id:
        raise FullStackIntegrationError("validation card missing claim_id")
    decision_payload = {
        "status": "needs_review",
        "reviewer_id": "full_stack_integration",
        "reviewer_note": "Integration round trip only; not a clinical validation.",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        decision_response = await client.post(
            f"{api_url.rstrip('/')}/api/v1/review-packets/{session_id}/claims/{claim_id}/validation",
            json=decision_payload,
        )
    if decision_response.status_code >= 400:
        raise FullStackIntegrationError(
            f"validation decision failed: {decision_response.status_code} {decision_response.text}"
        )
    async with httpx.AsyncClient(timeout=60) as client:
        export_response = await client.get(
            f"{api_url.rstrip('/')}/api/v1/review-packets/{session_id}/export"
        )
    if export_response.status_code >= 400:
        raise FullStackIntegrationError(
            f"review export fetch failed: {export_response.status_code} {export_response.text}"
        )
    export_payload = export_response.json()
    decisions = get_path(export_payload, "bundle.validation_decisions")
    if not isinstance(decisions, list) or not any(
        isinstance(decision, dict) and decision.get("claim_id") == claim_id
        for decision in decisions
    ):
        raise FullStackIntegrationError("validation decision was not persisted in export")
    return claim_id


async def validate_persistence_side_effects(
    *,
    packet: Mapping[str, object],
    requirements: Mapping[str, object],
    environment: Mapping[str, str],
) -> None:
    """Validate that OpenSearch and Postgres contain the processed packet."""
    session_id = str(packet["session_id"])
    opensearch = requirements.get("opensearch")
    postgres = requirements.get("postgres")
    if not isinstance(opensearch, dict) or not isinstance(postgres, dict):
        raise ValueError("persistence requirements are malformed")
    os_url = env_value(str(opensearch["url_env"]), environment) or str(opensearch["default_url"])
    query = {"query": {"term": {"session_id": session_id}}, "size": 1}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{os_url.rstrip('/')}/translume_evidence_claims/_search",
            json=query,
        )
    if response.status_code != 200:
        raise FullStackIntegrationError(
            f"OpenSearch claim query failed: {response.status_code} {response.text}"
        )
    hits = response.json().get("hits", {}).get("hits", [])
    if not hits:
        raise FullStackIntegrationError("OpenSearch has no evidence claim for session")
    dsn = env_value(str(postgres["dsn_env"]), environment) or str(postgres["default_dsn"])
    psycopg, _jsonb = _load_psycopg_for_integration()
    async with await psycopg.AsyncConnection.connect(dsn) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT count(*) FROM review_packets WHERE session_id = %(session_id)s",
                {"session_id": session_id},
            )
            row = await cursor.fetchone()
    if row is None or int(row[0]) < 1:
        raise FullStackIntegrationError("Postgres has no review packet for session")


async def run_full_stack_integration(
    *,
    requirements_path: Path,
    environment: Mapping[str, str],
    root: Path,
    wait_timeout_seconds: float,
    wait_interval_seconds: float,
    api_timeout_seconds: float,
) -> FullStackIntegrationResult:
    """Run the real Translume full-stack integration path.

    Acceptance criteria:
        1. Requires a real PDF path and real configured vLLM model.
        2. Requires API, Docling, MIMS, OpenSearch, Postgres, and vLLM services.
        3. Initializes OpenSearch indexes and Postgres tables against real services.
        4. Uploads the real PDF through the production API endpoint.
        5. Requires the review packet to contain all MVP evidence artifacts.
        6. Exercises human validation-card endpoints and persistence.
        7. Performs no mocked or fabricated service calls.
    """
    run_preflight(
        requirements_path=requirements_path,
        environment=environment,
        root=root,
        require_docker=False,
        require_gpu=False,
    )
    requirements = load_requirements(requirements_path)
    await wait_for_all_services(
        requirements,
        environment,
        timeout_seconds=wait_timeout_seconds,
        interval_seconds=wait_interval_seconds,
    )
    validate_retrieval_scope(requirements, environment)
    await validate_opensearch(requirements, environment)
    await validate_postgres(requirements, environment)
    await validate_vllm_structured_output(requirements, environment)
    report_path = Path(env_value("TRANSLUME_E2E_REPORT_PATH", environment)).expanduser().resolve()
    api_url = env_value("TRANSLUME_API_URL", environment) or "http://localhost:8080"
    report_type = env_value("TRANSLUME_E2E_REPORT_TYPE", environment) or "NGS"
    packet = await process_real_report(
        api_url=api_url,
        report_path=report_path,
        report_type=report_type,
        timeout_seconds=api_timeout_seconds,
    )
    checked_paths = assert_non_empty_paths(
        packet,
        tuple(str(path) for path in requirements.get("review_packet_required_non_empty_paths", [])),
    )
    assert_absent_phrases(
        packet,
        tuple(str(item) for item in requirements.get("review_packet_required_absent_phrases", [])),
    )
    await validate_persistence_side_effects(
        packet=packet,
        requirements=requirements,
        environment=environment,
    )
    claim_id = await validate_human_review_roundtrip(api_url=api_url, packet=packet)
    return FullStackIntegrationResult(
        case_id=str(packet["case_id"]),
        session_id=str(packet["session_id"]),
        claim_id=claim_id,
        checked_paths=checked_paths,
    )


def _load_psycopg_for_integration() -> tuple[Any, type[Any]]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as error:
        raise FullStackIntegrationError(
            "psycopg is required for full-stack integration; run `uv sync --all-groups`"
        ) from error
    return psycopg, Jsonb


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real Translume Docker/GPU/local-vLLM full-stack integration."
    )
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--wait-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--wait-interval-seconds", type=float, default=5.0)
    parser.add_argument("--api-timeout-seconds", type=float, default=900.0)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            run_full_stack_integration(
                requirements_path=args.requirements,
                environment=os.environ,
                root=ROOT,
                wait_timeout_seconds=args.wait_timeout_seconds,
                wait_interval_seconds=args.wait_interval_seconds,
                api_timeout_seconds=args.api_timeout_seconds,
            )
        )
    except (PreflightError, FullStackIntegrationError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        return 1
    print(json.dumps({"status": "ok", **result.__dict__}, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
