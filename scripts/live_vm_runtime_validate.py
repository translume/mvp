#!/usr/bin/env python3
"""Compatibility entry point for the Docker/CPU/OpenAI validation helper."""

from __future__ import annotations

if __package__:
    from .live_vm_runtime_validation import main
else:
    from live_vm_runtime_validation import main


if __name__ == "__main__":
    raise SystemExit(main())
