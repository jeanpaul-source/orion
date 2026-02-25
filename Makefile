.PHONY: lint format test test-full coverage typecheck

lint:
	.venv/bin/ruff check hal/ tests/ harvest/ eval/

format:
	.venv/bin/ruff format hal/ tests/ harvest/ eval/

test:
	.venv/bin/pytest tests/ --ignore=tests/test_intent.py -v

test-full:
	OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

coverage:
	.venv/bin/pytest tests/ --ignore=tests/test_intent.py --cov=hal --cov-report=term-missing

typecheck:
	.venv/bin/mypy hal/
