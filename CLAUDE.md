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
Lecture seule. Tout le travail se fait dans ce projet (`src/`, `tickets/`).

## Travail en cours

Ticket actif : **0002 — Construire un index global (JSON)**

L'index (`src/index.json`) est le seul artefact à construire et modifier.
Format : JSON, un objet par document, champs : `id`, `annee`, `auteurs`, `titre`,
`type`, `revue_editeur`, `fichier`, `statut_droits`, `hal_id`, `notes`.
