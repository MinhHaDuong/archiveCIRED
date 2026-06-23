Last updated: 2026-06-23T09:45Z

## North star

Rendre accessible la production scientifique du CIRED (1970–2013) aux chercheurs
CIRED et ENPC : collection Zotero privée partagée, PDFs attachés, métadonnées
structurées (~740 documents). Succès = un chercheur trouve et télécharge n'importe
quelle publication via Zotero, métadonnées correctes. Dépôt HAL différé.

## Status
<!-- generated 2026-06-23T09:45Z (à la main : refresh-STATE.py cassé, cf. 0027) -->
**Tickets:** 9 prêts · 2 bloqués (0015←0018+0019+0025, 0024←0022+0023) · 4 différés (0003/0005/0006/0007) — `erg ready tickets/`
**Catalogue:** base dédupliquée **686** notices ; recueil 50 ans d'Antonin **miroité** dans la collection « Recueil 50 ans CIRED » (key VPDB49CK, **131 items**) + tag `recueil-50ans`. Règle : apparier par **id, jamais par titre**.
**Index:** file_index 1991 fichiers (0010) · doc_index 1112 docs (0011) · CI make check (0012) · 81 tests passent.
**Recent commits:**
  b5dcbbc Encoder les arêtes du DAG de tickets (Blocked-by)
  885b282 Ticket 0026 (durcir match_untyped) + 0006 deferred de explore-prs
  6983a55 Migrer les tickets legacy Tag: → Label: (erg migrate)
  dfe1ef2 Ticket 0025 : recadrer l'audit « aucune perte d'information »
  2f6caff Ticket 0019 : cartographie des 131 notices du groupe (miroir)

## Chemin à suivre

1. **0025** — audit zéro-perte (lecture seule, exécutable maintenant). Vert ⇒
   groupe `Recueil_CIRED` supprimable ; avec 0018+0019 ferme le tracker 0015.
2. **0021** (normaliser auteurs) → swarms **0022**/**0023** (HAL/OpenAlex),
   **0024** en filet après. Mêmes notices : ≤8 agents, écritures revues.
3. Indépendant : **0020** (fonds Sachs). Opportuniste : **0026** (durcir matcher).

## Notes

- Recueil miroité mais **non vérifié** : ne pas supprimer le groupe avant 0025 vert.
  Dédoublonnage des ~48 copies injectées différé (`src/zotero_dedup.py`).
- Binaire committé `tickets/erg` obsolète (casse refresh-STATE.py) → 0027.
