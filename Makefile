PYTHONPATH := .:packages/translume-schemas/src:packages/translume-ports/src:packages/translume-core/src:packages/translume-clients/src:packages/translume-adapters/src:apps/translume-api/src:apps/translume-ui/src:services/docling-service/src:services/optimuskg-service/src:services/tooluniverse-service/src:services/medea-service/src:services/worker/src
export PYTHONPATH

.PHONY: up down build logs status test docker-config gradio-up gradio-down gradio-rebuild gradio-status gradio-logs integration-full-stack validate-prime-directives mims-data mims-data-status vendor-status init-postgres init-opensearch

up gradio-up:
	docker compose up --build -d

build:
	docker compose build

down gradio-down:
	docker compose down

gradio-rebuild:
	docker compose up --build -d --force-recreate

status gradio-status:
	docker compose ps -a

logs gradio-logs:
	docker compose logs --tail=200 -f

docker-config:
	docker compose config --quiet

test:
	docker build -f docker/test.Dockerfile -t translume-tests .
	docker run --rm --network none translume-tests python scripts/run_unit_tests.py

integration-full-stack:
	docker compose --profile verification run --rm verify

validate-prime-directives:
	docker compose exec translume-api python scripts/validate_prime_directives.py --force --output-dir /data/audit/runtime_diagnostics

mims-data:
	docker compose run --rm data-init

mims-data-status:
	docker compose exec medea-service python -c "from medea_service.database_runtime import inspect_medeadb; print(inspect_medeadb().as_dict())"
	docker compose exec optimuskg-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8091/health').read().decode())"

vendor-status:
	docker compose exec translume-api python -c "from pathlib import Path; from translume_core.vendor.packaged import require_packaged_vendor_sources; require_packaged_vendor_sources(Path('/app')); print('All bundled vendor sources verified')"

init-postgres:
	docker compose exec translume-api python scripts/init_postgres.py

init-opensearch:
	docker compose exec translume-api python scripts/init_opensearch.py
