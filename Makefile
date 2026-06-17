.PHONY: install test run export serve lint clean

install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

test:
	. .venv/bin/activate && ruff check src tests web && pytest -q && mypy src

run:
	. .venv/bin/activate && signal-connector run

export:
	. .venv/bin/activate && signal-connector export --out output/signals.json

serve:
	. .venv/bin/activate && PYTHONPATH=. python -m uvicorn web.app:app --host 127.0.0.1 --port 8000

# the Loom money-shot: fresh DB grows, second run dedupes
demo:
	. .venv/bin/activate && rm -f output/signals.db && signal-connector run && signal-connector run

clean:
	rm -f output/signals.db && rm -rf .cache .pytest_cache .ruff_cache .mypy_cache
