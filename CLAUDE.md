# archiveCIRED — Instructions projet

## Données source

L'archive numérisée est à :
```
/home/haduong/data/datasets/ours/Archives CIRED numerisées/
```

Structure :
- `docs/` — corpus principal (articles, rapports, chapitres, thèses, WP), 1970–2013
- `docs/TDMSachs/` — visualisations sigma.js du fonds Sachs (Tropes + OII template, F. Bordignon)
- `TDM/` — PDFs scannés originaux fonds Sachs (CIR_SAC_), 1970–1998
- `attente/à dédoublonner avec ce qui est déjà traité/` — 110 fichiers à réconcilier
- `attente/à traiter/GODARD/` — 211 fichiers biblio O. Godard 1991–2013

## Règle absolue

**Ne jamais modifier, déplacer, renommer ou supprimer de fichiers dans l'archive source.**
Lecture seule. Tout le travail se fait dans ce projet.

## Structure du projet

```
src/        scripts Python uniquement (build_index.py, dedup.py, …)
tests/      tests pytest
outputs/    artefacts générés (index.json, file_index.json, dedup_report.json, …)
tickets/    tickets de travail
docs/       documentation projet
```

`src/` ne contient pas de données. Les outputs vont dans `outputs/`.

## Architecture d'indexation (deux couches)

**Couche 1 — Index archivistique** (`outputs/file_index.json`, ticket 0010)
Un enregistrement par fichier physique, toute l'archive. 1 991 fichiers.
Champs : `fichier`, `taille`, `hash`, `ext`. Pas de champ `id` — `fichier` est la clé.

**Couche 2 — Index documentaire** (`outputs/doc_index.json`, ticket 0011)
Un enregistrement par document logique, toute l'archive. 1 112 documents.
Construit depuis `file_index.json` par groupement en 3 passes :
- Passe 1 : hash identique → doublon
- Passe 2 : `canonical_key(filename)` → variante de format (PDF+TXT, YYYY-NNN cross-dir)
- Passe 3 : correspondance Titre+Auteur+Année post-enrichissement → `groupe_incertain: true`

Champs : `id` (sha1 fichier principal), `fichiers` (liste avec rôles), `annee`, `auteurs`,
`titre`, `type`, `revue_editeur`, `statut_droits`, `hal_id`, `notes`, `groupe_incertain`.

Remplace `outputs/index.json` (ticket 0002, clos) qui couvrait uniquement `docs/`.
