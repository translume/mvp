#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "packages" / "translume-core" / "src"
if str(PACKAGE_PATH) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PATH))


class UIHealthCheckError(RuntimeError):
    """Raised when the Gradio UI health check fails."""


@dataclass(frozen=True)
class UIHealthResponse:
    """Represent the observed UI HTTP response.

    Attributes:
        status_code: HTTP status code returned by the UI endpoint.
        content_type: Response content type header.
        body: Decoded response body.
    """

    status_code: int
    content_type: str
    body: str


def ui_url_from_environment(environment: dict[str, str]) -> str:
    """Return the UI health URL from environment variables.

    Acceptance criteria:
        1. Determinism: Same environment returns same normalized URL.
        2. Defaults: Missing `TRANSLUME_UI_URL` uses localhost Gradio URL.
        3. Validation: Empty URL raises `UIHealthCheckError`.
        4. Normalization: Trailing slash is removed.

    Args:
        environment: Environment mapping.

    Returns:
        Normalized UI URL.

    Raises:
        UIHealthCheckError: If URL is empty.
    """
    value = environment.get("TRANSLUME_UI_URL", "http://localhost:7860").strip()
    if not value:
        raise UIHealthCheckError("TRANSLUME_UI_URL must not be empty")
    return value.rstrip("/")


def validate_ui_health_response(response: UIHealthResponse) -> None:
    """Validate that the Gradio UI returned a real HTTP response.

    Acceptance criteria:
        1. Status code must be HTTP 2xx.
        2. Response body must be non-empty.
        3. HTML or text content is accepted.
        4. No static success is fabricated by this function.

    Args:
        response: Observed UI HTTP response.

    Raises:
        UIHealthCheckError: If response is not a healthy UI response.
    """
    if response.status_code < 200 or response.status_code >= 300:
        raise UIHealthCheckError(f"UI returned HTTP {response.status_code}")
    if not response.body.strip():
        raise UIHealthCheckError("UI returned an empty response body")
    content_type = response.content_type.casefold()
    if "html" not in content_type and "text" not in content_type:
        raise UIHealthCheckError(
            f"UI returned unexpected content type: {response.content_type}"
        )


def fetch_ui_health(url: str, timeout_seconds: float) -> UIHealthResponse:
    """Fetch the Gradio UI root endpoint.

    Acceptance criteria:
        1. Performs one real HTTP request to the provided URL.
        2. Captures status code, content type, and response body.
        3. Raises `UIHealthCheckError` for network failures.
        4. Does not fabricate a success response.

    Args:
        url: UI root URL.
        timeout_seconds: Request timeout.

    Returns:
        Observed UI response.

    Raises:
        UIHealthCheckError: If the request fails.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return UIHealthResponse(
                status_code=int(response.status),
                content_type=response.headers.get("content-type", ""),
                body=body,
            )
    except urllib.error.URLError as error:
        raise UIHealthCheckError(f"UI request failed: {error}") from error


def main() -> int:
    """Run the live Gradio UI health check.

    Acceptance criteria:
        1. Uses the configured UI URL.
        2. Performs a real HTTP request.
        3. Returns non-zero when the UI is unavailable.
        4. Prints a concise status line for runtime diagnostics.
    """
    parser = argparse.ArgumentParser(description="Check the Gradio UI is reachable.")
    parser.add_argument("--url", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    url = args.url or ui_url_from_environment(dict(os.environ))
    try:
        response = fetch_ui_health(url, args.timeout_seconds)
        validate_ui_health_response(response)
    except UIHealthCheckError as error:
        print(f"ui_health=failed reason={error}")
        return 1
    print(f"ui_health=ok url={url} content_type={response.content_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
