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

# Appariement flou des docs sans clé d'archive ↔ notices Zotero — réseau au
# premier passage (met en cache outputs/zotero_notices.json), hors `make check`.
outputs/match_untyped_report.json: src/match_untyped.py outputs/doc_index.json
	uv run python src/match_untyped.py --output outputs/match_untyped_report.json

# Sélection des documents nouveaux du recueil 50 ans CIRED (ticket 0018) —
# pur, hors-ligne, depuis file_index.json.
outputs/recueil_new_docs.json: src/select_new_recueil.py outputs/file_index.json
	uv run python src/select_new_recueil.py --output outputs/recueil_new_docs.json

# RIS à importer pour les docs nouveaux (ticket 0018) — réseau au premier
# passage (notices du groupe privé), hors `make check`.
outputs/recueil_new_docs.ris: src/build_recueil_ris.py outputs/recueil_new_docs.json
	uv run python src/build_recueil_ris.py --output outputs/recueil_new_docs.ris

# Diff des corrections d'Antonin (groupe Recueil_CIRED → My Library) pour revue
# humaine — réseau (notices groupe + perso), hors `make check`.
outputs/recueil_corrections_report.json: src/diff_recueil.py src/match_untyped.py
	uv run python src/diff_recueil.py --output outputs/recueil_corrections_report.json

# Audit indépendant (ticket 0025) : aucune information perdue avant de supprimer
# le groupe Recueil_CIRED — réseau (notices groupe + My Library), lecture seule,
# hors `make check`.
outputs/verify_recueil_mirror_report.json outputs/verify_recueil_mirror_report.md: src/verify_recueil_mirror.py src/reconcile_zotero.py
	uv run python src/verify_recueil_mirror.py \
		--output-json outputs/verify_recueil_mirror_report.json \
		--output-md outputs/verify_recueil_mirror_report.md

# Comparaison fichier-par-fichier des 54 URL « recueil non dupliquée » (ticket
# 0029) : taille + SHA-256 des paires de taille égale — réseau + téléchargement
# de gros PDF, lecture seule, hors `make check`.
outputs/recueil_url_comparison.json outputs/recueil_url_comparison.md: src/compare_recueil_urls.py src/reconcile_zotero.py outputs/verify_recueil_mirror_report.json
	uv run python src/compare_recueil_urls.py --output outputs/recueil_url_comparison.json

# Résolution des stubs recueil (ticket 0018) : Crossref + OpenAlex + HAL pour les
# documents nouveaux sans métadonnée de groupe — réseau, lecture seule, hors
# `make check`. mailto = pool poli des APIs.
outputs/resolve_stubs_report.json outputs/resolve_stubs_report.md: src/resolve_stubs.py outputs/recueil_new_docs.json
	uv run python src/resolve_stubs.py --mailto minh.haduong@gmail.com --output outputs/resolve_stubs_report.json

check-fast:
	uv run pytest -m "not integration and not slow" tests/

check: check-fast
	uv run pytest tests/
