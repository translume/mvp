PYTHONPATH := .:packages/translume-schemas/src:packages/translume-ports/src:packages/translume-core/src:packages/translume-clients/src:packages/translume-adapters/src:apps/translume-api/src:apps/translume-ui/src:services/docling-service/src:services/optimuskg-service/src:services/tooluniverse-service/src:services/medea-service/src:services/worker/src
export PYTHONPATH
COMPOSE ?= docker compose
UV ?= uv
PYTHON ?= uv run python
PYTEST ?= uv run pytest
RUFF ?= uv run ruff

DATA_DIR ?= $(CURDIR)/data
MEDEA_DATA_HOST_DIR ?= $(DATA_DIR)/medea_cache
MEDEADB_PATH ?= $(MEDEA_DATA_HOST_DIR)/MedeaDB
MEDEADB_REVISION ?=
MEDEADB_MAX_WORKERS ?= 8
MEDEADB_FORCE_DOWNLOAD ?= false
OPTIMUSKG_DATA_HOST_DIR ?= $(DATA_DIR)/optimuskg_cache
OPTIMUSKG_CACHE_DIR ?= $(OPTIMUSKG_DATA_HOST_DIR)
OPTIMUSKG_USE_LCC ?= true
OPTIMUSKG_FORCE_DOWNLOAD ?= false

export MEDEA_DATA_HOST_DIR MEDEADB_PATH
export OPTIMUSKG_DATA_HOST_DIR OPTIMUSKG_CACHE_DIR OPTIMUSKG_USE_LCC

MEDEA_DATA_PYTHON ?= $(UV) run --no-project \
	--with 'huggingface-hub>=0.34,<1' \
	--with 'hf-xet>=1,<2' python
OPTIMUSKG_DATA_PYTHON ?= $(UV) run --no-project \
	--with 'polars>=1.19' \
	--with 'pyarrow>=19' \
	--with 'networkx>=3' \
	--with 'requests>=2.32' \
	--with 'platformdirs>=4' python

truthy = $(filter true TRUE True 1 yes YES Yes,$(strip $(1)))
MEDEA_FORCE_FLAG = $(if $(call truthy,$(MEDEADB_FORCE_DOWNLOAD)),--force,)
MEDEA_REVISION_FLAG = $(if $(strip $(MEDEADB_REVISION)),--revision "$(MEDEADB_REVISION)",)
OPTIMUSKG_FORCE_FLAG = $(if $(call truthy,$(OPTIMUSKG_FORCE_DOWNLOAD)),--force,)
OPTIMUSKG_LCC_FLAG = $(if $(call truthy,$(OPTIMUSKG_USE_LCC)),--use-lcc,--no-use-lcc)

.PHONY: \
	test lint docker-config validate-prime-directives \
	vendor-repos vendor-git-clone vendor-git-pull vendor-status \
	vendor-bootstrap-from-zips audit-vendor-model-calls catalog-vendor-repos \
	medea-data optimuskg-data mims-data mims-data-status prepare-full-stack \
	init-opensearch init-postgres docling-health preflight-full-stack \
	integration-full-stack-up integration-full-stack \
	integration-full-stack-down integration-full-stack-logs \
	live-vm-validate live-vm-validate-leave-up \
	live-vm-validate-down-on-failure live-vm-validation-logs \
	live-vm-validate-diagnostics live-vm-logs check-ui-health

test:
	$(PYTEST) -q

lint:
	$(RUFF) check .

docker-config:
	$(COMPOSE) config >/tmp/translume-compose.yaml

validate-prime-directives:
	$(PYTHON) scripts/validate_prime_directives.py --force

vendor-repos:
	$(PYTHON) scripts/vendor_repos.py

# Explicit aliases: production vendor management is Git-only.
vendor-git-clone: vendor-repos

vendor-git-pull: vendor-repos

vendor-status:
	$(PYTHON) scripts/vendor_status.py

# Offline bootstrap is for inspection only; it does not satisfy production status.
vendor-bootstrap-from-zips:
	$(PYTHON) scripts/vendor_from_zips.py --force

audit-vendor-model-calls:
	$(PYTHON) scripts/audit_vendor_model_calls.py

catalog-vendor-repos:
	$(PYTHON) scripts/catalog_vendor_repos.py

# Download the complete official MedeaDB snapshot into the host path mounted at
# /app/data/medea_cache/MedeaDB in medea-service.
medea-data: vendor-repos
	mkdir -p "$(MEDEA_DATA_HOST_DIR)"
	$(MEDEA_DATA_PYTHON) scripts/download_mims_data.py medea $(MEDEA_REVISION_FLAG) $(MEDEA_FORCE_FLAG) \
		--destination "$(MEDEADB_PATH)" \
		--max-workers "$(MEDEADB_MAX_WORKERS)"

# Use the real OptimusKG Python client so its DOI/version cache layout exactly
# matches the get_file() calls used by optimuskg-service.
optimuskg-data: vendor-repos
	mkdir -p "$(OPTIMUSKG_CACHE_DIR)"
	$(OPTIMUSKG_DATA_PYTHON) scripts/download_mims_data.py optimuskg $(OPTIMUSKG_LCC_FLAG) $(OPTIMUSKG_FORCE_FLAG) \
		--repo "$(CURDIR)/third_party/upstream/OptimusKG" \
		--cache-dir "$(OPTIMUSKG_CACHE_DIR)"

mims-data: medea-data optimuskg-data

mims-data-status:
	$(OPTIMUSKG_DATA_PYTHON) scripts/download_mims_data.py status \
		--medeadb "$(MEDEADB_PATH)" \
		--optimuskg-cache "$(OPTIMUSKG_CACHE_DIR)" \
		$(OPTIMUSKG_LCC_FLAG)

# Production preparation is deliberately mutating; preflight itself remains a
# read-only validation command.
prepare-full-stack: mims-data

init-opensearch:
	$(PYTHON) scripts/init_opensearch.py

init-postgres:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/init_postgres.py

docling-health:
	curl -fsS http://localhost:8090/health

preflight-full-stack:
	$(PYTHON) scripts/full_stack_preflight.py --require-docker --require-gpu

integration-full-stack-up: prepare-full-stack
	$(MAKE) preflight-full-stack
	$(COMPOSE) --profile gpu --profile docling up --build -d

integration-full-stack: integration-full-stack-up
	$(PYTHON) scripts/run_full_stack_integration.py

integration-full-stack-down:
	$(COMPOSE) --profile gpu --profile docling down

integration-full-stack-logs:
	$(COMPOSE) --profile gpu --profile docling logs --tail=200


live-vm-validate:
	$(PYTHON) scripts/live_vm_runtime_validate.py

live-vm-validate-diagnostics:
	$(PYTHON) scripts/live_vm_runtime_validate.py --continue-after-failure

live-vm-logs:
	$(COMPOSE) --profile gpu --profile docling logs --tail=300

check-ui-health:
	$(PYTHON) scripts/check_ui_health.py
