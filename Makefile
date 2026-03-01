.PHONY: lint lint-md format test test-full coverage typecheck check install-hooks dev-setup doc-drift

lint:
	.venv/bin/ruff check hal/ tests/ harvest/ eval/

lint-md:
	.venv/bin/pre-commit run markdownlint-cli2 --all-files

format:
	.venv/bin/ruff format hal/ tests/ harvest/ eval/

test:
	.venv/bin/pytest tests/ --ignore=tests/test_intent.py -v

test-full:
	OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

coverage:
	.venv/bin/pytest tests/ --ignore=tests/test_intent.py --cov=hal --cov-report=term-missing --cov-report=html

typecheck:
	.venv/bin/mypy hal/

doc-drift:
	.venv/bin/python scripts/check_doc_drift.py

check: lint typecheck test doc-drift

install-hooks:
	.venv/bin/pre-commit install --install-hooks --overwrite

dev-setup: ## Fresh clone → full enforcement in one command
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	.venv/bin/pre-commit install --install-hooks --overwrite
	@echo ""
	@echo "Dev environment ready. Hooks installed."
	@echo "  Run 'make check' to verify everything passes."
