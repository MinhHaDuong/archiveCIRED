ARCHIVE ?= /home/haduong/data/datasets/ours/Archives CIRED numerisées

.PHONY: check check-fast

src/dedup_report.json: src/dedup.py
	uv run python src/dedup.py \
		--docs "$(ARCHIVE)/docs" \
		--attente "$(ARCHIVE)/attente/à dédoublonner avec ce qui est déjà traité" \
		--output src/dedup_report.json

src/index.json: src/build_index.py
	uv run python src/build_index.py --output src/index.json --unresolved src/unresolved.csv

check-fast:
	uv run pytest -m "not integration and not slow" tests/

check: check-fast
	uv run pytest tests/
