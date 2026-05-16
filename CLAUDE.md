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

## Index archivistique (ticket 0010)

`outputs/file_index.json` — un enregistrement par fichier physique, toute l'archive.
Champs : `id` (sha1 du chemin), `fichier`, `taille`, `hash`, `ext`.

## Index bibliographique (ticket 0002, clos)

`outputs/index.json` — un enregistrement par document logique de `docs/`.
Champs : `id`, `annee`, `auteurs`, `titre`, `type`, `revue_editeur`, `fichier`,
`texte_ocr`, `statut_droits`, `hal_id`, `notes`.
