"""Load only the actual upstream Medea capabilities required by this service.

Medea's top-level initializer eagerly imports unrelated model-backed research
tools. Loading selected, unchanged files under a real service-owned namespace
retains its DepMap parser and OpenScholar code without executing that initializer.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from types import ModuleType

import medea_service.vendor_modules

_IMPORT_LOCK = Lock()
_NAMESPACE = "medea_service.vendor_modules"
_SOURCE_FILES = ("env_utils.py", "instructions.py", "depmap.py", "open_scholar.py")


class VendorRuntimeError(RuntimeError):
    """The real upstream source or a required service contract is unavailable."""


@dataclass(frozen=True)
class MedeaSourceRuntime:
    """References to verified, real upstream source and its DepMap parser."""

    repo_path: Path
    depmap_module: ModuleType
    source_sha256: dict[str, str]

    def new_open_scholar_module(self) -> ModuleType:
        """Load a private module so concurrent requests cannot rebind each other."""
        module = _load_source_module(
            "open_scholar",
            self.repo_path / "medea" / "tool_space" / "open_scholar.py",
            register=False,
        )
        parameters = inspect.signature(module.OpenScholar).parameters
        required = {
            "model",
            "tokenizer",
            "client_llm",
            "reranker",
            "use_contexts",
            "top_n",
        }
        if not required.issubset(parameters):
            raise VendorRuntimeError(
                "upstream OpenScholar constructor contract changed"
            )
        for name in (
            "run",
            "reranking_passages_cross_encoder",
            "reranking_passages_cross_encoder_supplemental",
        ):
            if not callable(getattr(module.OpenScholar, name, None)):
                raise VendorRuntimeError(f"upstream OpenScholar lacks {name}")
        # The NLTK package import does not load weights. Bind a pure sentence
        # boundary function so no Punkt resource is ever downloaded or executed.
        module.sent_tokenize = split_sentences
        return module


def split_sentences(text: str) -> list[str]:
    """Split text deterministically without a learned local tokenizer.

    Acceptance criteria:
        1. Retain all non-whitespace input content in original order.
        2. Preserve decimal-point tokens that contain no whitespace.
        3. Never load NLTK resources, a local model or a remote model.
    """
    return [part for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text) if part]


def import_vendor_module(
    repo_path: Path, module_names: tuple[str, ...]
) -> MedeaSourceRuntime:
    """Load real Medea parser/source files without importing unused model code.

    Acceptance criteria:
        1. Only the configured Medea source tree is accepted.
        2. Missing source and changed callable contracts fail explicitly.
        3. Source bytes remain unmodified and their hashes are reported.
        4. No dummy package, fake scientific result or dependency stub is used.
    """
    if module_names != ("medea",):
        raise VendorRuntimeError("MEDEA_MODULE_NAMES must be medea")
    root = repo_path.resolve()
    source = root / "medea" / "tool_space"
    missing = [name for name in _SOURCE_FILES if not (source / name).is_file()]
    if missing:
        raise VendorRuntimeError("Medea source is incomplete: " + ", ".join(missing))
    digests = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in _SOURCE_FILES
    }
    with _IMPORT_LOCK:
        _load_source_module("env_utils", source / "env_utils.py", register=True)
        _load_source_module("instructions", source / "instructions.py", register=True)
        depmap = _load_source_module("depmap", source / "depmap.py", register=True)
    if not callable(getattr(depmap, "GeneCorrelationLookup", None)):
        raise VendorRuntimeError("Medea DepMap parser lacks GeneCorrelationLookup")
    runtime = MedeaSourceRuntime(root, depmap, digests)
    runtime.new_open_scholar_module()
    return runtime


def _load_source_module(name: str, path: Path, *, register: bool) -> ModuleType:
    full_name = f"{_NAMESPACE}.{name}"
    existing = sys.modules.get(full_name)
    if register and existing is not None:
        if Path(str(existing.__file__)).resolve() != path.resolve():
            raise VendorRuntimeError(
                "Medea source root cannot change during service lifetime"
            )
        return existing
    specification = importlib.util.spec_from_file_location(full_name, path)
    if specification is None or specification.loader is None:
        raise VendorRuntimeError(f"cannot load upstream Medea source: {path.name}")
    module = importlib.util.module_from_spec(specification)
    try:
        specification.loader.exec_module(module)
    except (ImportError, OSError, AttributeError) as error:
        raise VendorRuntimeError(
            f"cannot import upstream Medea {path.name}: {type(error).__name__}"
        ) from error
    if register:
        sys.modules[full_name] = module
        setattr(medea_service.vendor_modules, name, module)
    return module
