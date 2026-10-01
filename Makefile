ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PY := $(ROOT)/.venv/bin/python
PNPM := pnpm --dir "$(ROOT)"
DB_STARTUP_TIMEOUT ?= 120
POSTGRES_BIN ?=

.PHONY: api api-offline api-cloudflare web db-up migrate contracts check check-api check-web check-skeleton check-chat check-rag check-tools check-mcp check-agent tool-image live-spike live-holdout review-holdout

api: migrate
	AGENT_LAB_PERSISTENCE=1 "$(PY)" -m uvicorn agent_lab_api.main:app --app-dir "$(ROOT)/apps/api" --host 127.0.0.1 --port 18761

api-offline:
	"$(PY)" -m uvicorn agent_lab_api.main:app --app-dir "$(ROOT)/apps/api" --host 127.0.0.1 --port 18761

api-cloudflare: migrate
	"$(PY)" "$(ROOT)/apps/api/live_server.py"

db-up:
	docker compose --project-directory "$(ROOT)" -f "$(ROOT)/compose.yaml" up -d --wait --wait-timeout $(DB_STARTUP_TIMEOUT) db

migrate: db-up
	PYTHONPATH="$(ROOT)/apps/api" "$(PY)" -m agent_lab_api.database

web:
	$(PNPM) dev

contracts:
	"$(PY)" "$(ROOT)/apps/api/export_contract.py"
	$(PNPM) --filter @ai-agent-lab/web generate:types

check-api:
	"$(ROOT)/.venv/bin/ruff" check "$(ROOT)/apps/api"
	"$(ROOT)/.venv/bin/ruff" format --check "$(ROOT)/apps/api"
	"$(PY)" -m pytest -c "$(ROOT)/apps/api/pyproject.toml" "$(ROOT)/apps/api/tests" -m "not integration"

check-web:
	$(PNPM) lint
	$(PNPM) test
	$(PNPM) build

check: check-api check-web
	python3 "$(ROOT)/docs/plans/2026-10-01-rebuild/check_plan.py" --self-test

check-skeleton:
	$(PNPM) test:e2e

check-chat:
	"$(PY)" "$(ROOT)/apps/api/check_chat.py" --ready-timeout $(DB_STARTUP_TIMEOUT) $(if $(POSTGRES_BIN),--postgres-bin "$(POSTGRES_BIN)",)

check-rag:
	"$(PY)" "$(ROOT)/apps/api/check_chat.py" --suite rag --mutation --ready-timeout $(DB_STARTUP_TIMEOUT) $(if $(POSTGRES_BIN),--postgres-bin "$(POSTGRES_BIN)",)

tool-image:
	docker pull python:3.14.7-slim-bookworm

check-tools: tool-image
	"$(PY)" "$(ROOT)/apps/api/check_tools.py" --browser
	"$(PY)" -m pytest -c "$(ROOT)/apps/api/pyproject.toml" "$(ROOT)/apps/api/tests/test_terminal.py"

check-mcp:
	"$(PY)" "$(ROOT)/apps/api/check_mcp.py"

check-agent:
	"$(PY)" "$(ROOT)/apps/api/check_agent.py"
	"$(PY)" "$(ROOT)/apps/api/check_chat.py" --suite agent --ready-timeout $(DB_STARTUP_TIMEOUT) $(if $(POSTGRES_BIN),--postgres-bin "$(POSTGRES_BIN)",)

live-spike:
	"$(PY)" "$(ROOT)/apps/api/live_spike.py"

live-holdout:
	"$(PY)" "$(ROOT)/apps/api/check_chat.py" --suite holdout --ready-timeout $(DB_STARTUP_TIMEOUT) $(if $(POSTGRES_BIN),--postgres-bin "$(POSTGRES_BIN)",)

review-holdout:
	"$(PY)" "$(ROOT)/apps/api/review_holdout.py" --attempt "$(ATTEMPT)" --review "$(REVIEW)" --reviewer "$(REVIEWER)"
