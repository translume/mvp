PYTHONPATH := .:packages/translume-schemas/src:packages/translume-ports/src:packages/translume-core/src:packages/translume-clients/src:packages/translume-adapters/src:apps/translume-api/src:apps/translume-ui/src:services/docling-service/src:services/optimuskg-service/src:services/tooluniverse-service/src:services/medea-service/src:services/worker/src
export PYTHONPATH
COMPOSE ?= docker compose

.PHONY: test lint docker-config validate-prime-directives vendor-repos vendor-git-clone vendor-git-pull vendor-status vendor-bootstrap-from-zips audit-vendor-model-calls catalog-vendor-repos init-opensearch init-postgres docling-health preflight-full-stack integration-full-stack-up integration-full-stack integration-full-stack-down integration-full-stack-logs live-vm-validate live-vm-validate-leave-up live-vm-validate-down-on-failure live-vm-validation-logs live-vm-validate live-vm-validate-diagnostics live-vm-logs check-ui-health

test:
	pytest -q

lint:
	ruff check .

docker-config:
	$(COMPOSE) config >/tmp/translume-compose.yaml

validate-prime-directives:
	python scripts/validate_prime_directives.py --force

vendor-repos:
	python scripts/vendor_repos.py

# Explicit aliases: production vendor management is Git-only.
vendor-git-clone: vendor-repos

vendor-git-pull: vendor-repos

vendor-status:
	python scripts/vendor_status.py

# Offline bootstrap is for inspection only; it does not satisfy production status.
vendor-bootstrap-from-zips:
	python scripts/vendor_from_zips.py --force

audit-vendor-model-calls:
	python scripts/audit_vendor_model_calls.py

catalog-vendor-repos:
	python scripts/catalog_vendor_repos.py

init-opensearch:
	python scripts/init_opensearch.py

init-postgres:
	PYTHONPATH=$(PYTHONPATH) python scripts/init_postgres.py

docling-health:
	curl -fsS http://localhost:8090/health

preflight-full-stack:
	python scripts/full_stack_preflight.py --require-docker --require-gpu

integration-full-stack-up: preflight-full-stack
	$(COMPOSE) --profile gpu --profile docling up --build -d

integration-full-stack: integration-full-stack-up
	python scripts/run_full_stack_integration.py

integration-full-stack-down:
	$(COMPOSE) --profile gpu --profile docling down

integration-full-stack-logs:
	$(COMPOSE) --profile gpu --profile docling logs --tail=200


live-vm-validate:
	python scripts/live_vm_runtime_validate.py

live-vm-validate-diagnostics:
	python scripts/live_vm_runtime_validate.py --continue-after-failure

live-vm-logs:
	$(COMPOSE) --profile gpu --profile docling logs --tail=300

check-ui-health:
	python scripts/check_ui_health.py
