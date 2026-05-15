.PHONY: check check-fast

src/index.json: src/build_index.py
	uv run python src/build_index.py --output src/index.json --unresolved src/unresolved.csv

check-fast:
	uv run pytest -m "not integration and not slow" tests/

check: check-fast
	uv run pytest tests/
