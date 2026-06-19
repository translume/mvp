# AGENTS.md

# Repository Instructions for Codex

Before doing any work in this repository, read these files in full:

1. `CODING_STANDARDS.md`
2. `README.md`
3. `DEVELOPER.md` (if it is avaliable)
4. `STRUCTURED_OUTPUTS.md`
5. `QUICKSTART.md`

`CODING_STANDARDS.md` is authoritative for code style, design patterns,
functional-programming practices, and docstrings.

The section titled **“Docstrings With Acceptance Criteria”** in
`CODING_STANDARDS.md` is authoritative for docstring format, acceptance
criteria, and implementation style.

`README.md` is the basic user-facing how-to guide.

If present in the repo, `DEVELOPER.md` is the developer onboarding guide. It should explain project
structure, commands, flags, parameters, expected behavior, testing instructions,
development workflow, and each file’s purpose.

`STRUCTURED_OUTPUTS.md` documents how structured outputs should be used with
vLLM.

---

## Engineering Principles

All code must be:

1. Composable.
2. Testable.
3. Small in scope.
4. Functional-programming oriented.
5. Referentially transparent wherever practical.
6. Free from unintended side effects.
7. Limited to the approved scope.
8. Deterministic wherever possible.
9. Explicit about validation and error handling.
10. Clear enough for humans and AI agents to reason about.

Prefer pure functions.

Use immutable data structures where practical.

Use frozen dataclasses for simple domain records when appropriate.

Avoid hidden mutation, mutable global state, and implicit side effects.

Isolate I/O, mutation, network access, filesystem access, database access,
model serving, subprocess calls, and other side effects behind clearly named
boundary functions.

Do not use `assert` for argument validation. Use explicit exceptions such as
`ValueError` or `TypeError`.

Catch specific exceptions. Avoid bare `except:` and avoid catching `Exception`
unless re-raising as a precise domain exception.

---

## Ticket-Based Workflow

Treat every requested feature, bug fix, refactor, documentation update, or
configuration change as a single JIRA-style ticket.

Work on only one chunk of functionality at a time.

Before writing code, produce a numbered implementation plan for review.

Stop after producing the plan. Do not write code until the plan is approved.

The plan must include:

1. Task summary.
2. Functional requirements.
3. Acceptance criteria.
4. Files expected to change.
5. New or modified functions, modules, classes, or types.
6. Test strategy.
7. Documentation updates.
8. Dependency/version research.
9. Docker or Docker Compose build/run plan.
10. Edge cases and assumptions.
11. Explicitly out-of-scope items.

---

## After Plan Approval

Once the plan is approved:

1. Implement only what the approved plan describes.
2. Do not introduce unrelated refactors.
3. Do not introduce unapproved dependencies.
4. Do not alter public behavior outside the approved scope.
5. Do not introduce hidden side effects.
6. Add or update tests for the approved functionality.
7. Update documentation only when required by the approved scope.
8. Keep implementation aligned with `CODING_STANDARDS.md`.
9. Ensure docstrings include acceptance criteria as required.
10. Preserve the approved scope exactly.

If a requested change appears to require scope expansion, stop and ask for plan
approval before implementing the expanded scope.

---

## Python Style Requirements

Follow the Python style rules in `CODING_STANDARDS.md`.

Default expectations:

1. Use `from __future__ import annotations` where useful.
2. Use full package imports where practical.
3. Avoid wildcard imports.
4. Group imports in this order:
   1. Future imports.
   2. Standard library.
   3. Third-party packages.
   4. Local modules.
5. Use modern type annotations such as `str | None`, `list[int]`, and
   `dict[str, str]`.
6. Prefer `Sequence`, `Mapping`, and other abstract collection types for input
   parameters when appropriate.
7. Use `TypeAlias` for type aliases.
8. Use descriptive type variables such as `_ItemT`.
9. Avoid mutable default arguments.
10. Keep functions small and focused.
11. Prefer refactoring functions that grow beyond roughly 40 lines.
12. Use one statement per line.
13. Use four-space indentation.
14. Limit lines to 80 characters unless a documented exception applies.
15. Use two blank lines between top-level definitions.
16. Use one blank line between methods.
17. Use f-strings or logging parameter interpolation appropriately.
18. For logging, call logging functions with a pattern string and parameters,
    not f-strings.
19. Use context managers for files, sockets, and stateful resources.
20. Place executable script logic in `main()`.
21. Guard executable scripts with:

```python
if __name__ == "__main__":
    raise SystemExit(main())
````

---

## Functional-Programming Requirements

Prefer functional-programming style.

Use small, composable functions.

Design pure functions wherever possible.

Pure functions must:

1. Return the same result for the same inputs.
2. Avoid mutating arguments.
3. Avoid reading or writing hidden global state.
4. Avoid I/O.
5. Avoid network calls.
6. Avoid filesystem calls.
7. Avoid time-dependent behavior unless time is passed in explicitly.
8. Avoid random behavior unless randomness is passed in explicitly.
9. Return new values instead of mutating existing values.

When side effects are required, isolate them in clearly named boundary
functions. Keep domain logic pure and side-effect-free.

Prefer dispatch tables over long `if`/`elif` chains when mapping keys to
operations.

Use comprehensions and generator expressions for simple transformations when
they improve clarity.

Avoid clever, overly dense, or hard-to-debug functional code.

---

## Docstrings With Acceptance Criteria

For pure functions, FP pipelines, domain transformations, validation functions,
and public APIs, include docstrings with explicit acceptance criteria.

Use this structure where applicable:

```python
def example_function(input_value: str) -> str:
    """Return a normalized value.

    Acceptance criteria:
        1. Determinism: Same input returns the same result.
        2. No mutation: Do not mutate caller-owned values.
        3. Validation: Invalid input raises `ValueError`.
        4. Normalization: Output is stripped and lowercased.

    Args:
        input_value: Raw input string.

    Returns:
        Normalized string.

    Raises:
        ValueError: If `input_value` is empty after stripping.
    """
```

Acceptance criteria should be specific, testable, and aligned with the approved
plan.

---

## Testing Requirements

Add or update tests for every behavior change.

Tests should verify:

1. Determinism.
2. No mutation of inputs where applicable.
3. Correct return values.
4. Validation behavior.
5. Raised exceptions.
6. Edge cases listed in the approved plan.
7. Boundary behavior for I/O or side-effect wrapper functions.
8. Structured-output behavior where relevant.

Prefer testing pure functions directly.

Do not skip tests unless explicitly approved in the plan.

---

## Dependency and Version Requirements

Before proposing, adding, removing, or changing dependencies:

1. Research the latest stable versions of the relevant dependencies.
2. Document the selected versions.
3. Explain why those versions were selected.
4. Include dependency changes in the implementation plan.
5. Wait for approval before changing dependency files.

Do not add or upgrade dependencies unless the approved plan explicitly includes
them.

Do not rely on stale dependency assumptions.

---

## Docker Requirements

Use Docker or Docker Compose as the primary build and run workflow.

Do not rely on local host execution as the primary workflow.

Use this Python Docker base image by default unless the approved plan explicitly
says otherwise:

```dockerfile
FROM python:3.12.13-slim
```

Always include the Docker or Docker Compose build/run plan in the numbered
implementation plan.

---

## Docker Compose GPU Syntax

When GPU access is required in Docker Compose, use this syntax:

```yaml
gpus:
  - device_ids: ["0"]
    capabilities: ["gpu"]
```

Do not replace this with older or alternate GPU syntax unless the approved plan
explicitly requires it.

---

## vLLM Command Syntax

When configuring the Granite Docling vLLM service, use this command syntax:

```yaml
command: >
  ibm-granite/granite-docling-258M
  --revision untied
  --host 0.0.0.0
  --port 8000
  --dtype bfloat16
  --max-model-len 8192
  --max-num-seqs 512
  --max-num-batched-tokens 8192
  --gpu-memory-utilization 0.90
  --enable-chunked-prefill
  --structured-outputs-config.backend=auto
  --limit-mm-per-prompt '{"image":1}'
```

Do not alter this command unless the approved plan explicitly requires a change.

---

## Structured Outputs Requirements

Structured outputs allow model generation to be constrained to a predefined
format such as:

1. JSON schema.
2. Fixed choice list.
3. Regular expression.
4. Context-free grammar.

Use the structured-output backend flag when serving vLLM with structured-output
support:

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --structured-outputs-config.backend=auto
```

The `--structured-outputs-config.backend` option selects the backend used to
enforce constraints. The default value `auto` chooses a backend automatically.

Refer to `STRUCTURED_OUTPUTS.md` before changing structured-output behavior.

---

## Documentation Requirements

Maintain these documentation files:

### `README.md`

`README.md` is the user-facing how-to guide.

It should explain:

1. What the project does.
2. How to install or build it.
3. How to configure it.
4. How to run it.
5. How to use it.
6. Common examples.
7. Troubleshooting notes where useful.

### `DEVELOPER.md`

If this file is available read `DEVELOPER.md` is the developer onboarding guide.

It must include:

1. Project structure overview.
2. File-by-file explanation of the codebase.
3. Table of available commands.
4. Command flags.
5. Command parameters.
6. Expected command behavior.
7. Docker and Docker Compose workflows.
8. Testing instructions.
9. Development workflow notes.

### `STRUCTURED_OUTPUTS.md`

`STRUCTURED_OUTPUTS.md` documents structured-output usage with vLLM.

Update it when structured-output behavior, vLLM command syntax, supported schema
types, or server configuration changes.

---

## When to Update Documentation

Update `README.md`, `DEVELOPER.md`, or `STRUCTURED_OUTPUTS.md` whenever the
approved change affects:

1. User behavior.
2. Developer workflow.
3. Commands.
4. Flags.
5. Parameters.
6. Setup steps.
7. Docker usage.
8. Docker Compose usage.
9. Dependency versions.
10. Project structure.
11. vLLM serving behavior.
12. Structured-output behavior.

Do not update documentation for unrelated content.

---

## Scope Control

Do not:

1. Write code before plan approval.
2. Implement functionality outside the approved plan.
3. Refactor unrelated code.
4. Add unapproved dependencies.
5. Change public behavior outside the approved scope.
6. Introduce hidden global state.
7. Add mutable module-level state unless explicitly approved.
8. Use local host execution as the primary workflow.
9. Skip tests for behavior changes.
10. Change Docker, GPU, or vLLM syntax unless explicitly approved.

---

## Role Expectation

Act like a senior software engineer.

Be precise, conservative in scope, and quality-focused.

Favor clear, maintainable, well-tested code over clever implementations.

When uncertain, document the assumption in the plan before implementing.

Never expand scope silently.