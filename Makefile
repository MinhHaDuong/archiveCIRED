ARCHIVE ?= /home/haduong/data/datasets/ours/Archives CIRED numerisées

.PHONY: check check-fast

outputs/attic/dedup_report.json: src/dedup.py
	uv run python src/dedup.py \
		--docs "$(ARCHIVE)/docs" \
		--attente "$(ARCHIVE)/attente/à dédoublonner avec ce qui est déjà traité" \
		--output outputs/attic/dedup_report.json

outputs/index.json: src/build_index.py
	uv run python src/build_index.py --output outputs/index.json --unresolved outputs/attic/unresolved.csv

outputs/file_index.json outputs/file_index.csv: src/build_file_index.py
	uv run python src/build_file_index.py \
		--archive-dir "$(ARCHIVE)" \
		--output-json outputs/file_index.json \
		--output-csv outputs/file_index.csv

outputs/doc_index.json: src/build_doc_index.py outputs/file_index.json outputs/index.json
	uv run python src/build_doc_index.py \
		--archive-dir "$(ARCHIVE)" \
		--output outputs/doc_index.json

# Réconciliation avec le catalogue Zotero distant — nécessite réseau +
# ~/.config/keys/zotero-archive-cired.env (hors `make check` exprès).
outputs/reconcile_report.json: src/reconcile_zotero.py outputs/doc_index.json
	uv run python src/reconcile_zotero.py --output outputs/reconcile_report.json

check-fast:
	uv run pytest -m "not integration and not slow" tests/

check: check-fast
	uv run pytest tests/
