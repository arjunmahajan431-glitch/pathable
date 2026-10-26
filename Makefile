# PathAble developer commands.
#
#   make setup    install Python and browser dependencies (needs uv and Node)
#   make data     download/caches the OpenStreetMap walking graph
#   make dev      run API + frontend
#   make check    lint, type-check, unit/component tests
#   make e2e      start both servers and run Playwright + axe
#   make evaluate regenerate one seeded report per city under docs/

SHELL := /bin/bash
PY := backend/.venv/bin/python
UV := uv
NPM := npm

.PHONY: setup data coverage elevation dev api check backend-check frontend-check \
        e2e e2e-install evaluate audit clean

setup:
	cd backend && $(UV) sync
	cd frontend && $(NPM) ci

data:
	$(PY) scripts/fetch_data.py --all
	$(PY) scripts/coverage_report.py --all

coverage:
	$(PY) scripts/coverage_report.py --all

elevation:
	$(PY) scripts/fetch_elevation.py --all

dev:
	./scripts/dev.sh

api:
	cd backend && .venv/bin/uvicorn pathable.api.main:app --reload --port 8000

check: backend-check frontend-check

backend-check:
	cd backend && .venv/bin/ruff check pathable tests ../scripts
	cd backend && .venv/bin/ruff format --check pathable tests ../scripts
	cd backend && .venv/bin/mypy
	cd backend && .venv/bin/pytest

frontend-check:
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) test

e2e-install:
	cd frontend && npx playwright install chromium

e2e:
	cd frontend && $(NPM) run e2e

evaluate:
	$(PY) scripts/evaluate.py --demo --pairs 40
	$(PY) scripts/evaluate.py --demo --area saint-paul-mn --pairs 40

audit:
	@if [[ -z "$(FILE)" ]]; then echo "Usage: make audit FILE=data/fixtures/sample_field_audit.csv"; exit 2; fi
	$(PY) scripts/import_audit.py "$(FILE)" $${ARGS:-}

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache frontend/dist
