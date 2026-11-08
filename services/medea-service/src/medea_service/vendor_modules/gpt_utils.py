"""Real OpenAI completion boundary for narrow-loaded upstream modules.

Each owned OpenScholar instance is rebound to its request-scoped pooled
completion adapter. Direct calls to this import boundary also use OpenAI.
"""

from __future__ import annotations

from typing import Any


def chat_completion(*args: Any, **kwargs: Any) -> str:
    """Execute the compatible upstream signature through the official API."""
    from medea_service.openai_runtime import (
        OpenAICompletion,
        build_openai_client,
        build_openai_medea_config,
    )

    config = build_openai_medea_config()
    client = build_openai_client(config)
    try:
        return OpenAICompletion(client, config)(*args, **kwargs)
    finally:
        client.close()
