# FP Python Style Guide Cheat Sheet

This cheat sheet integrates the Google Python Style Guide with
functional-programming principles and dataclass usage. It uses rich
docstring patterns with acceptance criteria to produce code that is clear,
deterministic, and easy for humans and AI agents to reason about.

## 1. Background

Python is Google's main dynamic language; the style guide codifies best
practices. Teams often use auto-formatters such as Black or Pyink to enforce
consistency.

Linting tools such as `pylint` catch easy-to-miss errors, including typos and
unused variables. Use the provided `pylintrc` where available and disable
warnings sparingly with `# pylint: disable=<rule>`.

The FP mindset favors referentially transparent code that is free of hidden
side effects. Pure functions, immutable data structures, explicit contracts,
and deterministic behavior make programs easier to test and maintain.

## 2. Python Language Rules

### 2.1 Lint

Run `pylint` on code. Suppress warnings only when justified, and document the
reason.

```python
import logging


# pylint: disable=unused-argument
# Unused param is required by API.
def handle_event(event: str, unused_context: str) -> None:
    """Handle an event.

    Args:
        event: Event name or payload summary.
        unused_context: Required by the external API but unused here.
    """
    logging.info("event: %s", event)
```

### 2.2 Imports

Use imports for packages and modules. Do not import individual classes or
functions unless local style already does so or the import is a stable
exception. Avoid wildcard imports.

Group imports in this order: future imports, standard library, third-party
packages, then local modules. Use full package names and avoid ambiguous
relative imports.

```python
from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from typing import Final, TypeAlias

import numpy as np

from myproject.utils import helpers


FloatVec: TypeAlias = Iterable[float]


def mean(values: FloatVec) -> float:
    """Return the arithmetic mean of a sequence of floats.

    Args:
        values: Input floating-point values.

    Returns:
        Arithmetic mean.
    """
    seq = list(values)
    return sum(seq) / len(seq)
```

### 2.3 Packages

Import each module using its full package path. This prevents unintended
imports through `sys.path` and makes code discoverable.

```python
from myproject.backend.analytics import metrics

# Avoid ambiguous imports:
# import metrics
```

### 2.4 Exceptions

Use built-in exceptions such as `ValueError` and `TypeError` for API misuse.
Never use `assert` for argument validation. Catch specific exceptions and name
them with `as`. Avoid bare `except:` and avoid catching `Exception` unless
re-raising as a precise domain exception. Keep `try` blocks small and use
`finally` or context managers for cleanup.

```python
class InvalidConfigError(Exception):
    """Raised when configuration values are invalid."""


def load_config(path: str) -> dict[str, str]:
    """Load key/value pairs from a file.

    Args:
        path: Path to the configuration file.

    Returns:
        Mapping of configuration keys to values.

    Raises:
        FileNotFoundError: If the file does not exist.
        InvalidConfigError: If the file cannot be parsed.
    """
    try:
        with open(path, encoding="utf-8") as file_obj:
            pairs = [line.strip().split(" = ") for line in file_obj]
    except FileNotFoundError:
        raise
    except ValueError as error:
        raise InvalidConfigError(f"invalid config: {error}") from error

    return {key: value for key, value in pairs}
```

### 2.5 Mutable Global State

Avoid mutable module-level state. Prefer constants marked with `Final` or
immutable dataclasses. If global state is necessary, hide it behind accessor
functions and document why.

```python
from dataclasses import dataclass
from typing import Final


CONFIG_PATH: Final[str] = "/etc/myapp/config"


@dataclass(frozen=True)
class AppConfig:
    """Read-only application configuration.

    Attributes:
        retries: Number of retries.
        timeout: Request timeout in seconds.
    """

    retries: int
    timeout: float


_config_cache: AppConfig | None = None


def get_config() -> AppConfig:
    """Return application configuration, loading it once."""
    global _config_cache
    if _config_cache is None:
        _config_cache = parse_config(CONFIG_PATH)
    return _config_cache
```

### 2.6 Nested Functions and Closures

Use nested functions only to close over local variables. Do not nest functions
just to hide helpers; define private helpers at module level with a leading
underscore. Capture loop variables by defaulting them in lambdas or inner
functions.

```python
from collections.abc import Callable


def make_power(exponent: int) -> Callable[[int], int]:
    """Return a function that raises its argument to `exponent`.

    Args:
        exponent: Power to apply.

    Returns:
        Function that raises a base to `exponent`.
    """

    def power(base: int, *, exp: int = exponent) -> int:
        return base**exp

    return power
```

### 2.7 Comprehensions and Generator Expressions

Use comprehensions for simple transformations. Prefer one `for` and one
optional `if`. Avoid complex nested comprehensions; use a regular loop for
clarity. Prefer generator expressions for single-use iteration.

```python
squares = [value * value for value in range(5)]
positive_sum = sum(value for value in [-1, 2, 3, -4] if value > 0)
```

### 2.8 Default Iterators and Operators

Iterate directly over containers. Do not call `dict.keys()` or
`file.readlines()` unless the method itself is required.

```python
values = {"a": 1, "b": 2}

for key in values:
    print(key)
```

### 2.9 Generators

Use generators when lazy evaluation reduces memory usage or improves
readability. Generator docstrings must include a `Yields:` section.

```python
from collections.abc import Generator


def fibonacci(limit: int) -> Generator[int, None, None]:
    """Generate Fibonacci numbers up to and including `limit`.

    Args:
        limit: Maximum emitted value.

    Yields:
        Next Fibonacci number no greater than `limit`.
    """
    first = 0
    second = 1
    while first <= limit:
        yield first
        first, second = second, first + second
```

### 2.10 Lambda Functions

Use lambdas only for short throwaway expressions. Never assign a lambda to a
variable.

```python
strings = ["apple", "banana", "cherry"]
strings.sort(key=lambda item: len(item))
```

### 2.11 Conditional Expressions

Ternary expressions are fine for simple cases. For complex conditions or
nested ternaries, use a full `if`/`else` statement.

```python
status = "enabled" if condition else "disabled"
```

### 2.12 Default Argument Values

Never use mutable defaults. Use `None` and create new objects inside the
function. For dataclasses, use `field(default_factory=list)`.

```python
from collections.abc import Sequence


def extend_list(
    item: int,
    collection: Sequence[int] | None = None,
) -> list[int]:
    """Return a new list with `item` appended.

    Args:
        item: Integer to append.
        collection: Optional existing sequence.

    Returns:
        A new list containing `collection` and `item`.
    """
    values = [] if collection is None else list(collection)
    values.append(item)
    return values
```

### 2.13 Properties

Use properties for trivial computations or validation. Avoid properties for
expensive operations or side effects.

```python
import math


class Circle:
    """Represent a circle."""

    def __init__(self, radius: float) -> None:
        self._radius = radius

    @property
    def radius(self) -> float:
        """Return the radius in metres."""
        return self._radius

    @radius.setter
    def radius(self, value: float) -> None:
        if value < 0:
            raise ValueError("radius must be non-negative")
        self._radius = value

    @property
    def area(self) -> float:
        """Return the area of the circle."""
        return math.pi * (self._radius**2)
```

### 2.14 True/False Evaluations

Use implicit truthiness for containers. Check for `None` explicitly with
`is None` or `is not None`.

```python
users: list[str] | None = []

if users:
    print(f"{len(users)} users")
else:
    print("no users")

value: int | None = 0
if value is None:
    print("value missing")
elif value == 0:
    print("value is zero")
```

### 2.16 Lexical Scoping

Nested functions capture variables from outer scopes. Capture loop variables
with default arguments when needed.

```python
from collections.abc import Callable


def make_adders(nums: list[int]) -> list[Callable[[], int]]:
    """Return functions that return the corresponding numbers."""
    return [lambda value=value: value for value in nums]
```

### 2.17 Function and Method Decorators

Use decorators judiciously. Decorators run at definition time and can hide side
effects. Always apply `functools.wraps`. Prefer module functions over
`@staticmethod`; use `@classmethod` only for alternative constructors.

```python
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any


def debug(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that prints function call details for debugging."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        print(f"Calling {func.__name__} with {args} and {kwargs}")
        result = func(*args, **kwargs)
        print(f"{func.__name__} returned {result}")
        return result

    return wrapper
```

### 2.18 Threading

Do not rely on atomicity of built-in types. Protect shared state with
`threading.Lock` or use `queue.Queue`. Prefer high-level concurrency
primitives.

```python
import threading


class Counter:
    """Thread-safe counter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def increment(self) -> int:
        """Increment and return the counter value."""
        with self._lock:
            self._value += 1
            return self._value
```

### 2.19 Power Features

Avoid metaclasses, bytecode hacks, dynamic inheritance, reflection, and import
hacks. Prefer dataclasses, `enum.Enum`, or `__init_subclass__`.

```python
from typing import Any


class Plugin:
    """Base class for auto-registering plugins."""

    registry: dict[str, type] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        Plugin.registry[cls.__name__] = cls
```

### 2.20 Modern Python

Use `from __future__ import annotations` where forward references or cleaner
typing are useful.

```python
from __future__ import annotations


class Node:
    """Linked-list node."""

    def __init__(self, value: int, next_node: Node | None = None) -> None:
        self.value = value
        self.next_node = next_node
```

### 2.21 Type Annotated Code

Annotate functions and variables. Use `str | None` instead of
`Optional[str]`, and `list[int]` instead of `List[int]`. Use `Sequence`,
`Mapping`, and related abstract collection types when appropriate. Use
`TypeVar` for generics and `Protocol` for structural typing.

```python
from typing import Generic, Protocol, TypeVar


_ItemT = TypeVar("_ItemT")


class Stack(Generic[_ItemT]):
    """A simple LIFO stack."""

    def __init__(self) -> None:
        self._items: list[_ItemT] = []

    def push(self, item: _ItemT) -> None:
        """Push an item onto the stack."""
        self._items.append(item)

    def pop(self) -> _ItemT:
        """Remove and return the most recent item."""
        return self._items.pop()


class Drawable(Protocol):
    """Protocol for renderable objects."""

    def draw(self) -> str:
        """Return a rendered representation."""


def render(obj: Drawable) -> str:
    """Render an object using structural typing."""
    return obj.draw()
```

## 3. Python Style Rules

### 3.1 Semicolons

Do not use semicolons to terminate statements or place two statements on one
line.

### 3.2 Line Length

Limit lines to 80 characters. Exceptions include long import statements, URLs,
and module-level constants. Break long expressions inside parentheses,
brackets, or braces; do not use backslashes for continuation.

```python
result = my_function(
    first_argument,
    second_argument,
    third_argument,
    fourth_argument,
)
```

### 3.3 Parentheses

Use parentheses sparingly. Do not wrap conditions or return values unless
needed for line continuation or to indicate a tuple.

```python
if condition:
    do_something()

names = ("Alice",)
```

### 3.4 Indentation and Trailing Commas

Indent with four spaces. Use hanging indents for long expressions and align
closing brackets with the line that started the expression. Use trailing
commas when the closing bracket is on its own line.

```python
values = (
    1,
    2,
    3,
)
```

### 3.5 Blank Lines

Use two blank lines between top-level definitions, one blank line between
methods, and no blank line immediately after a `def` line.

### 3.6 Whitespace

No spaces inside parentheses, brackets, or braces. Use spaces after commas and
around binary operators. Do not place spaces before commas. Do not align
assignments or comments vertically.

```python
items = [1, 2, 3]
for index, value in enumerate(items):
    print(index, value)
```

### 3.7 Shebang Line

Use `#!/usr/bin/env python3` at the top of scripts intended to be executed
directly. Omit it in import-only modules.

### 3.8 Comments and Docstrings

Module docstrings start with a summary line, then a blank line, then a
description of the module's purpose and examples when useful.

Class docstrings describe what the class represents and document public
attributes in an `Attributes:` section.

Function and method docstrings document non-obvious functions and include
`Args:`, `Returns:`, `Raises:`, and optionally `Yields:`.

Inline comments explain tricky code. Place two spaces before `#` and begin
with a capital letter. Avoid describing the obvious; comments should explain
why, not what.

```python
import secrets


class User:
    """Represent a user account.

    Attributes:
        username: Login name.
        email: Primary email address.
    """

    def __init__(self, username: str, email: str) -> None:
        self.username = username
        self.email = email

    def reset_password(self) -> str:
        """Generate a random password.

        Returns:
            New random password string.
        """
        # Use a cryptographically secure random generator.
        return secrets.token_urlsafe(12)
```

### 3.10 Strings, Logging, and Error Messages

Use f-strings, `%` formatting, or `str.format()` for interpolation. Avoid
repeated string concatenation inside loops. Call logging functions with a
pattern string and parameters, not f-strings. Error messages should precisely
match the error condition and make interpolated parts identifiable.

```python
import logging


try:
    value = 1 / 0
except ZeroDivisionError as error:
    logging.error("Division error: %s", error)
```

### 3.11 Files, Sockets, and Stateful Resources

Always close files, sockets, and similar resources. Use `with` or
`contextlib.closing()`.

```python
with open("data.csv", encoding="utf-8") as csv_file:
    for line in csv_file:
        process(line)
```

### 3.12 TODO Comments

Use `# TODO: link-or-bug - explanation`. Include a tracker link or event.
Avoid naming individuals.

```python
# TODO: https://issuetracker.google.com/12345 - Remove fallback after migration.
```

### 3.13 Import Formatting

Use one import per line, except for grouped imports from `typing` or
`collections.abc`. Sort imports alphabetically within each group and separate
groups with blank lines.

### 3.14 Statements

Use one statement per line. A single-line `if` with no `else` is allowed only
for very small actions, but multiline form is preferred in this repo.

### 3.15 Getters and Setters

Provide explicit getters and setters only when getting or setting is complex
or expensive. Otherwise, expose attributes directly or use properties.

### 3.16 Naming

Use `lower_with_under` for functions, variables, and modules. Use `CapWords`
for classes and exceptions. Use `CAPS_WITH_UNDER` for constants. Avoid
single-letter names except loop counters and `f` as a file handle. Name type
variables descriptively, for example `_ItemT`.

### 3.17 Main

Place main logic in a `main()` function. Guard execution with:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

When using `absl.app`, call `app.run(main)`.

### 3.18 Function Length

Prefer small, focused functions. Consider refactoring if a function grows
beyond about 40 lines.

### 3.19 Type Annotations

Follow indentation guidelines when breaking signatures across lines. Use
forward references through `from __future__ import annotations` or quotes. Use
explicit `X | None`. Use `TypeAlias` for type aliases and name aliases in
`CapWords` style. Use `default_factory` for mutable dataclass fields.

## Functional Programming Principles and Patterns

Functional programming emphasizes pure functions, immutability, and
composition. These ideas make code easier to test and reason about.

### Referential Transparency and Pure Functions

Referential transparency means a function always returns the same result for
the same inputs and has no observable side effects. Avoid mutating inputs or
global state. Document purity with acceptance criteria in the docstring.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DomainRow:
    """Represent a domain row.

    Attributes:
        age: Age value.
        income: Income value.
        spend: Spend value.
        city: City name.
    """

    age: int
    income: float
    spend: float
    city: str


def scale_income(row: DomainRow, factor: float) -> DomainRow:
    """Return a new `DomainRow` with income scaled by `factor`.

    Acceptance criteria:
        1. Determinism: The same `row` and `factor` return the same result.
        2. No mutation: Do not modify `row`; return a new `DomainRow`.
        3. Correct scaling: `income` becomes `row.income * factor`.
        4. Preserve other fields: `age`, `spend`, and `city` remain unchanged.

    Args:
        row: Input domain record.
        factor: Multiplier to apply to income.

    Returns:
        New `DomainRow` with scaled income.
    """
    return DomainRow(
        age=row.age,
        income=row.income * factor,
        spend=row.spend,
        city=row.city,
    )
```

### Dispatch Tables Instead of Conditionals

Instead of long `if`/`elif` chains, use a dictionary that maps keys to
callables. Each operation should be a pure function where possible.

```python
from collections.abc import Callable, Mapping


Operation = Callable[[float, float], float]


def add(first: float, second: float) -> float:
    """Return the sum of two numbers."""
    return first + second


def sub(first: float, second: float) -> float:
    """Return the difference of two numbers."""
    return first - second


def mul(first: float, second: float) -> float:
    """Return the product of two numbers."""
    return first * second


def div(first: float, second: float) -> float:
    """Return the quotient of two numbers."""
    if second == 0:
        raise ZeroDivisionError("division by zero")
    return first / second


OPERATIONS: Mapping[str, Operation] = {
    "add": add,
    "sub": sub,
    "mul": mul,
    "div": div,
}


def calculate(op: str, first: float, second: float) -> float:
    """Perform a named arithmetic operation.

    Acceptance criteria:
        1. Determinism: Same inputs produce the same result.
        2. No mutation: Operations do not mutate state.
        3. Error handling: Unknown operations raise `KeyError`.

    Args:
        op: Operation name.
        first: First operand.
        second: Second operand.

    Returns:
        Operation result.

    Raises:
        KeyError: If `op` is unsupported.
        ZeroDivisionError: If `op` is `"div"` and `second` is zero.
    """
    return OPERATIONS[op](first, second)
```

### Higher-Order Functions and Lambdas

Higher-order functions take functions as arguments or return functions. Use
built-ins such as `sum`, `any`, `all`, and `functools.reduce` when they improve
clarity. Use small lambdas for simple callbacks, but prefer named functions for
non-trivial logic.

```python
from functools import reduce


numbers = [1, 2, 3, 4, 5]
doubled = list(map(lambda value: value * 2, numbers))
evens = [value for value in numbers if value % 2 == 0]
product = reduce(lambda acc, value: acc * value, numbers, 1)
contains_negative = any(value < 0 for value in numbers)
```

### Avoiding Imperative Loops and Conditionals

Prefer declarative transformations for simple map/filter logic. Use
comprehensions and mapping functions instead of manual loops when readability
improves. Replace long `if`/`elif` chains with dispatch tables.

```python
items = ["apple", "banana", "cherry", "date"]
results = [item.upper() for item in items if len(item) > 5]

categories = {"apple": "fruit", "carrot": "vegetable"}
kind = categories.get("banana", "unknown")
```

### Docstrings With Acceptance Criteria

When writing pure functions and FP pipelines, document behavior explicitly.
Enumerate acceptance criteria such as determinism, lack of mutation, and
validation rules. Use `Args:`, `Returns:`, and `Raises:`.

```python
def clip_age(spec: FeatureSpec, row: DomainRow) -> DomainRow:
    """Return a new `DomainRow` with `age` clipped to spec bounds.

    Acceptance criteria:
        1. Determinism: Same `(spec, row)` returns the same result.
        2. No mutation: Do not modify `row`; return a new `DomainRow`.
        3. Inclusive clipping: Values outside bounds are clipped to bounds.
        4. Preserve other fields: Income, spend, and city remain unchanged.
        5. Spec validation: If `age_clip_lo > age_clip_hi`, raise `ValueError`.

    Args:
        spec: Feature specification defining clipping bounds.
        row: Input domain row.

    Returns:
        New domain row with age clipped within bounds.

    Raises:
        ValueError: If the spec bounds are invalid.
    """
    if spec.age_clip_lo > spec.age_clip_hi:
        raise ValueError("age_clip_lo > age_clip_hi")

    age = max(min(row.age, spec.age_clip_hi), spec.age_clip_lo)
    return DomainRow(
        age=age,
        income=row.income,
        spend=row.spend,
        city=row.city,
    )
```

## 4. Parting Words

Be consistent. When editing existing code, match local style and avoid
introducing patterns that clash with surrounding code. The goal is readability
and maintainability. Combining Google's style guide with FP principles yields
code that is idiomatic, pure, deterministic, and testable.

Write clear docstrings with acceptance criteria, prefer pure functions and
immutable data structures, and follow the language and style rules summarized
above. This makes code easier for humans and AI systems to understand.