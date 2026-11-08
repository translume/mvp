"""Pure adaptation from public Pydantic schemas to OpenAI strict schemas."""

from __future__ import annotations

from copy import deepcopy

_TIGHT_OUTPUT_SCHEMAS = frozenset(
    {
        "ActionableBiologyOutput",
        "BiomarkerWatchListOutput",
        "ClaimEvidenceListOutput",
        "ConfirmatoryTestingOutput",
        "_BoundedConfirmatoryTestingOutput",
        "NextTestRecommendationsOutput",
        "RankedTreatmentOptionsOutput",
        "ResistanceForecastOutput",
        "RetestingTriggersOutput",
        "TranslationalAssessmentOutput",
        "TreatmentPressureMapOutput",
    }
)
_UNSUPPORTED_COMPOSITION = frozenset(
    {"allOf", "oneOf", "not", "if", "then", "else", "dependentSchemas"}
)


def to_openai_strict_schema(schema: dict[str, object]) -> dict[str, object]:
    """Require every declared field without changing its nullable semantics.

    Acceptance criteria:
        1. Caller-owned schemas are not mutated.
        2. All object schemas are closed and declare every property required.
        3. Existing unions, bounds, and references retain their semantics.
        4. A property named ``default`` is retained; schema defaults are removed.
        5. Open-ended maps/unsupported composition fail before remote I/O.
    """
    result = _normalize_node(deepcopy(schema), path="$", property_name=None)
    if result.get("type") != "object" and "$ref" not in result:
        raise ValueError("OpenAI structured output requires an object root schema")
    if "anyOf" in result:
        raise ValueError("OpenAI structured output cannot use an anyOf root")
    return result


def _normalize_node(
    schema: dict[str, object], *, path: str, property_name: str | None
) -> dict[str, object]:
    unsupported = sorted(set(schema) & _UNSUPPORTED_COMPOSITION)
    if unsupported:
        raise ValueError(
            f"Unsupported strict schema composition at {path}: {unsupported}"
        )
    result = {key: value for key, value in schema.items() if key != "default"}
    for key in ("$defs", "definitions", "properties"):
        mapping = result.get(key)
        if isinstance(mapping, dict):
            result[key] = {
                name: _normalize_node(
                    value, path=f"{path}.{key}.{name}", property_name=name
                )
                if isinstance(value, dict)
                else value
                for name, value in mapping.items()
            }
    for key in ("items", "contains"):
        value = result.get(key)
        if isinstance(value, dict):
            result[key] = _normalize_node(
                value, path=f"{path}.{key}", property_name=property_name
            )
    branches = result.get("anyOf")
    if isinstance(branches, list):
        result["anyOf"] = [
            _normalize_node(
                value, path=f"{path}.anyOf[{index}]", property_name=property_name
            )
            if isinstance(value, dict)
            else value
            for index, value in enumerate(branches)
        ]
    if result.get("type") == "object" or "properties" in result:
        properties = result.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"Object properties must be a mapping at {path}")
        additional = result.get("additionalProperties")
        if isinstance(additional, dict) or additional is True:
            raise ValueError(f"Open-ended object maps are not supported at {path}")
        result["properties"] = properties
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


def bounded_generation_schema(
    schema: dict[str, object], *, schema_name: str
) -> dict[str, object]:
    """Add generation-only bounds while retaining all stricter public bounds.

    Acceptance criteria:
        1. Public Pydantic schemas remain unchanged.
        2. Bounds apply only to schema nodes, never arbitrary enum/default data.
        3. Narrative Markdown keeps its dedicated larger character allowance.
    """
    max_items = 12 if schema_name in _TIGHT_OUTPUT_SCHEMAS else 20
    max_chars = 700 if schema_name in _TIGHT_OUTPUT_SCHEMAS else 1200
    return _bound_node(
        to_openai_strict_schema(schema),
        max_items=max_items,
        max_chars=max_chars,
        property_name=None,
    )


def _bound_node(
    schema: dict[str, object],
    *,
    max_items: int,
    max_chars: int,
    property_name: str | None,
) -> dict[str, object]:
    result = deepcopy(schema)
    for key in ("$defs", "definitions", "properties"):
        mapping = result.get(key)
        if isinstance(mapping, dict):
            result[key] = {
                name: _bound_node(
                    value, max_items=max_items, max_chars=max_chars, property_name=name
                )
                if isinstance(value, dict)
                else value
                for name, value in mapping.items()
            }
    items = result.get("items")
    if isinstance(items, dict):
        result["items"] = _bound_node(
            items, max_items=max_items, max_chars=max_chars, property_name=property_name
        )
    branches = result.get("anyOf")
    if isinstance(branches, list):
        result["anyOf"] = [
            _bound_node(
                value,
                max_items=max_items,
                max_chars=max_chars,
                property_name=property_name,
            )
            if isinstance(value, dict)
            else value
            for value in branches
        ]
    if result.get("type") == "array":
        existing = result.get("maxItems")
        result["maxItems"] = (
            min(existing, max_items) if type(existing) is int else max_items
        )
    if result.get("type") == "string":
        limit = 12000 if property_name == "markdown" else max_chars
        existing = result.get("maxLength")
        result["maxLength"] = min(existing, limit) if type(existing) is int else limit
    return result
