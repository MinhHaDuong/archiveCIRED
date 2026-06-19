# Réconciliation doc_index ↔ Zotero distant

Généré par `src/reconcile_zotero.py` (données JSON détaillées : `reconcile_report.json`).

## Source

- **Catalogue Zotero** : bibliothèque perso (1 378 notices) + groupe privé
  `Recueil_CIRED` (id 2511149, 131 notices) → **638 clés d'archive distinctes**.
- **Notre index** : `doc_index.json` (1 112 documents logiques).
- **Clé de jointure** : le nom de fichier d'archive (`CIR_SAC_0317`,
  `ENPC00_AR_LEESU_0012`, …), présent à la fois dans nos `fichiers[].fichier`
  et dans l'URL `inari.centre-cired.fr/.../docs/<nom>.pdf` des notices Zotero.

## Résultat

| | docs |
|---|---|
| Total index | 1 112 |
| Déjà catalogués dans Zotero (match par clé) | **829** |
| À ajouter (clé absente de Zotero) | **1** |
| Sans clé d'archive (non rattachables par nom) | **282** |
| Clés Zotero orphelines (dans Zotero, hors index) | **0** |

### Couverture par fonds

| Fonds | index | catalogue |
|---|---|---|
| CIR_SAC | 581 | 581 |
| ENPC_LEESU | 180 | 180 |
| CIR_GOD | 55 | 54 |
| CIR_GEN | 10 | 10 |
| CIR_HOU | 9 | 9 |

Le fonds structuré est catalogué à ~100 %. Seul `CIR_GOD_0017` (1997, Revue de
l'Énergie) manque.

### Les 282 docs sans clé d'archive

Répartition par type : 193 `null`, 87 `non-classifié`, 1 thèse, 1 rapport. Ce
sont les documents à noms descriptifs (Godard) et le corpus mal typé. Ils ne
peuvent pas être appariés par nom de fichier ; déterminer s'ils sont déjà dans
Zotero demande un appariement titre/auteur/année — **phase suivante**.

## Conséquence pour le ticket 0008

La prémisse « générer 1 112 notices et les importer dans un groupe vide » est
caduque : le catalogue existe déjà (probablement la numérisation inari /
F. Bordignon). Le travail restant est étroit :

1. Appariement titre/auteur des 282 docs non typés contre les 1 378 notices.
2. Ajout du seul manquant identifié (`CIR_GOD_0017`).
3. Audit de qualité des métadonnées des notices existantes.
4. Décision : attacher les vrais PDF dans Zotero (autonomie vs dépendance à
   inari) — hors périmètre de la réconciliation.

## Reproduire

```bash
uv run python src/reconcile_zotero.py     # nécessite réseau + ~/.config/keys/zotero-archive-cired.env
```
