ARCHIVE ?= /home/haduong/data/datasets/ours/Archives CIRED numerisées

.PHONY: check check-fast

outputs/dedup_report.json: src/dedup.py
	uv run python src/dedup.py \
		--docs "$(ARCHIVE)/docs" \
		--attente "$(ARCHIVE)/attente/à dédoublonner avec ce qui est déjà traité" \
		--output outputs/dedup_report.json

outputs/index.json: src/build_index.py
	uv run python src/build_index.py --output outputs/index.json --unresolved outputs/unresolved.csv

outputs/file_index.json outputs/file_index.csv: src/build_file_index.py
	uv run python src/build_file_index.py \
		--output-json outputs/file_index.json \
		--output-csv outputs/file_index.csv

check-fast:
	uv run pytest -m "not integration and not slow" tests/

check: check-fast
	uv run pytest tests/
