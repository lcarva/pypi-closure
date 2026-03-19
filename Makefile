VENV := .venv
PIP := $(VENV)/bin/pip
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: help setup fetch analyze run test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install .

setup: $(VENV)/bin/activate ## Create venv and install dependencies

fetch: setup ## Fetch data from ClickPy into data/
	$(PYTHON) fetch_data.py

analyze: setup ## Run analysis on fetched data, write report/
	$(PYTHON) analyze.py

run: fetch analyze ## Fetch data then run analysis

test: setup ## Run tests
	$(PIP) install '.[test]'
	PYTHONPATH=. $(PYTEST) tests/ -v

clean: ## Remove venv and generated files
	rm -rf $(VENV) data/ report/
