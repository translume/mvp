.PHONY: install install-dev lint typecheck test check schema dry-run

PYTHON ?= python
INPUT ?=
OUTPUT ?= precision_oncology_outputs

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	ruff check precision_oncology_pipeline.py tests examples

typecheck:
	mypy --ignore-missing-imports precision_oncology_pipeline.py tests/test_pipeline.py examples/run_as_library.py

test:
	$(PYTHON) -m pytest

check: lint typecheck test

schema:
	$(PYTHON) precision_oncology_pipeline.py --emit-schema-only --output-dir schemas

dry-run:
	@test -n "$(INPUT)" || (echo "Usage: make dry-run INPUT=/path/to/input.json" && exit 2)
	$(PYTHON) precision_oncology_pipeline.py --input "$(INPUT)" --output-dir "$(OUTPUT)" --dry-run
