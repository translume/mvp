PYTHONPATH := .:packages/translume-schemas/src:packages/translume-ports/src:packages/translume-core/src:packages/translume-clients/src:packages/translume-adapters/src:apps/translume-api/src:apps/translume-ui/src:services/docling-service/src:services/optimuskg-service/src:services/tooluniverse-service/src:services/medea-service/src:services/worker/src
export PYTHONPATH

TRANSLUME_ENV_FILE ?= .env
COMPOSE ?= docker compose --env-file $(TRANSLUME_ENV_FILE)
export TRANSLUME_ENV_FILE
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
	check-vllm-model check-ui-dockerfile check-local-data-ignore \
	vendor-repos vendor-status \
	medea-data optimuskg-data mims-data mims-data-status prepare-full-stack \
	reactome-image reactome-status reactome-smoke \
	wait-postgres wait-opensearch wait-vllm-clinical wait-vllm-docling wait-foundation-services wait-ui \
	init-postgres init-opensearch \
	gradio-up gradio-down gradio-logs gradio-status gradio-rebuild \
	full-stack-up full-stack-down full-stack-logs full-stack-status

test:
	$(PYTEST) -q

lint:
	$(RUFF) check .

docker-config:
	$(COMPOSE) config >/tmp/translume-compose.yaml

validate-prime-directives:
	$(PYTHON) scripts/validate_prime_directives.py --force

check-vllm-model:
	@if [ -z "$$VLLM_MODEL" ] && ! grep -q '^VLLM_MODEL=' .env 2>/dev/null; then \
		echo ""; \
		echo "ERROR: VLLM_MODEL is not set."; \
		echo ""; \
		echo "Add it to .env before starting the full stack."; \
		echo ""; \
		echo "Example:"; \
		echo "VLLM_MODEL=your-local-or-huggingface-clinical-model-id"; \
		echo ""; \
		exit 1; \
	fi

check-ui-dockerfile:
	@if [ ! -f docker/ui.Dockerfile ]; then \
		echo ""; \
		echo "ERROR: docker/ui.Dockerfile is missing."; \
		echo ""; \
		echo "Restore docker/ui.Dockerfile before running the Gradio UI stack."; \
		echo ""; \
		exit 1; \
	fi

check-local-data-ignore:
	@mkdir -p "$(DATA_DIR)"
	@if [ -f .gitignore ] && ! grep -q '^data/medea_cache/' .gitignore 2>/dev/null; then \
		echo "WARNING: data/medea_cache/ is not ignored in .gitignore."; \
		echo "Recommended: add data/medea_cache/ to .gitignore because MedeaDB is local runtime data."; \
	fi
	@if [ -f .gitignore ] && ! grep -q '^data/optimuskg_cache/' .gitignore 2>/dev/null; then \
		echo "WARNING: data/optimuskg_cache/ is not ignored in .gitignore."; \
		echo "Recommended: add data/optimuskg_cache/ to .gitignore because OptimusKG cache is local runtime data."; \
	fi

vendor-repos:
	$(PYTHON) scripts/vendor_repos.py

vendor-status:
	$(PYTHON) scripts/vendor_status.py

medea-data: vendor-repos
	mkdir -p "$(MEDEA_DATA_HOST_DIR)"
	$(MEDEA_DATA_PYTHON) scripts/download_mims_data.py medea $(MEDEA_REVISION_FLAG) $(MEDEA_FORCE_FLAG) \
		--destination "$(MEDEADB_PATH)" \
		--max-workers "$(MEDEADB_MAX_WORKERS)"

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

reactome-image:
	$(COMPOSE) pull reactome-graphdb

reactome-status:
	$(COMPOSE) ps reactome-graphdb tooluniverse-service
	curl -fsS "$${TOOLUNIVERSE_PUBLIC_URL:-http://localhost:8092}/health" | $(PYTHON) -m json.tool

reactome-smoke:
	$(PYTHON) scripts/smoke_local_reactome_workflow.py \
		--base-url "$${TOOLUNIVERSE_PUBLIC_URL:-http://localhost:8092}" \
		--expected-release "$${REACTOME_RELEASE:?set REACTOME_RELEASE}"

prepare-full-stack: check-local-data-ignore mims-data reactome-image

wait-postgres:
	@echo "Waiting for Postgres..."
	@for i in $$(seq 1 60); do \
		if docker exec mvp-postgres-1 pg_isready -U translume -d translume >/dev/null 2>&1; then \
			echo "Postgres is ready."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "ERROR: Postgres did not become ready."; \
	$(COMPOSE) logs --tail=100 postgres; \
	exit 1

wait-opensearch:
	@echo "Waiting for OpenSearch..."
	@for i in $$(seq 1 90); do \
		if curl -fsS http://localhost:9200/_cluster/health >/dev/null 2>&1; then \
			echo "OpenSearch is ready."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "ERROR: OpenSearch did not become ready."; \
	$(COMPOSE) logs --tail=100 opensearch; \
	exit 1

wait-vllm-clinical:
	@echo "Waiting for clinical vLLM..."
	@for i in $$(seq 1 180); do \
		if curl -fsS http://localhost:8000/v1/models >/dev/null 2>&1; then \
			echo "Clinical vLLM is ready."; \
			exit 0; \
		fi; \
		sleep 5; \
	done; \
	echo "ERROR: clinical vLLM did not become ready."; \
	$(COMPOSE) --profile gpu logs --tail=100 vllm-clinical; \
	exit 1

wait-vllm-docling:
	@echo "Waiting for Docling vLLM..."
	@for i in $$(seq 1 180); do \
		if curl -fsS http://localhost:8001/v1/models >/dev/null 2>&1; then \
			echo "Docling vLLM is ready."; \
			exit 0; \
		fi; \
		sleep 5; \
	done; \
	echo "ERROR: Docling vLLM did not become ready."; \
	$(COMPOSE) --profile gpu --profile docling logs --tail=100 vllm-docling; \
	exit 1

wait-foundation-services: wait-postgres wait-opensearch wait-vllm-clinical wait-vllm-docling

wait-ui:
	@echo "Waiting for Gradio UI..."
	@for i in $$(seq 1 90); do \
		if curl -fsS http://localhost:7860 >/dev/null 2>&1; then \
			echo "Gradio UI is ready."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "ERROR: Gradio UI did not become ready."; \
	$(COMPOSE) --profile gpu --profile docling logs --tail=150 translume-ui; \
	exit 1

init-postgres:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/init_postgres.py \
		--dsn "$${POSTGRES_PUBLIC_DSN:-postgresql://translume:translume@localhost:5432/translume}"

init-opensearch:
	OPENSEARCH_URL="$${OPENSEARCH_PUBLIC_URL:-http://localhost:9200}" \
		$(PYTHON) scripts/init_opensearch.py

gradio-up: check-vllm-model check-ui-dockerfile prepare-full-stack
	$(MAKE) vendor-status
	$(MAKE) mims-data-status
	$(COMPOSE) --profile gpu --profile docling down --remove-orphans
	$(COMPOSE) --profile gpu --profile docling up --build -d postgres opensearch vllm-clinical vllm-docling
	$(MAKE) wait-foundation-services
	$(MAKE) init-postgres
	$(MAKE) init-opensearch
	$(COMPOSE) --profile gpu --profile docling up --build -d \
		precision-oncology-pipeline dynamic-pathway-analyzer \
		translume-api translume-ui
	$(MAKE) wait-ui
	@echo ""
	@echo "Translume Gradio UI is ready here:"
	@echo "http://localhost:7860"
	@echo ""
	@echo "Useful commands:"
	@echo "  make gradio-status"
	@echo "  make gradio-logs"
	@echo "  make gradio-down"
	@echo ""

gradio-rebuild: check-vllm-model check-ui-dockerfile
	$(COMPOSE) --profile gpu --profile docling down --remove-orphans
	$(COMPOSE) --profile gpu --profile docling build --no-cache
	$(COMPOSE) --profile gpu --profile docling up -d \
		precision-oncology-pipeline dynamic-pathway-analyzer \
		translume-api translume-ui
	$(MAKE) wait-ui
	@echo ""
	@echo "Translume Gradio UI is ready here:"
	@echo "http://localhost:7860"
	@echo ""

gradio-down:
	$(COMPOSE) --profile gpu --profile docling down

gradio-logs:
	$(COMPOSE) --profile gpu --profile docling logs -f --tail=200

gradio-status:
	$(COMPOSE) --profile gpu --profile docling ps

full-stack-up: gradio-up

full-stack-down: gradio-down

full-stack-logs: gradio-logs

full-stack-status: gradio-status
