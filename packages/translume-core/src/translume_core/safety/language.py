from __future__ import annotations


class SafetyLanguageError(ValueError):
    """Raised when unsafe treatment-directing language is detected."""


def validate_safety_language(text: str, banned_phrases: list[str]) -> None:
    """Reject treatment-directing language.

    Acceptance criteria:
        1. Detects banned phrases case-insensitively.
        2. Raises SafetyLanguageError on unsafe text.
        3. Allows non-treatment-directing terms such as molecular fit.
        4. Function is pure.

    Args:
        text: Text to inspect.
        banned_phrases: Phrases that are not allowed.

    Raises:
        SafetyLanguageError: If banned language is present.
    """
    normalized = text.casefold()
    for phrase in banned_phrases:
        if phrase.casefold() in normalized:
            raise SafetyLanguageError(f"unsafe treatment-directing language: {phrase}")
