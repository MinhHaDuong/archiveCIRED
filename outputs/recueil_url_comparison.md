# Comparaison des URL « recueil non dupliquée » (54 paires)

Généré par `src/compare_recueil_urls.py`. Données : `recueil_url_comparison.json`. **Lecture seule, aucune décision.**

Chaque notice du groupe Recueil_CIRED pointe une URL inari ; My Library porte un document équivalent sous **une autre URL inari** (deux buckets distincts). On compare les deux fichiers, sans en supprimer aucun.

## Synthèse

- **Fichiers distincts** (taille différente, ou SHA-256 différent) : **1**
- Vrais doublons (SHA-256 identiques) : **0** sur 32 de taille égale
- Sans PDF des deux côtés (métadonnée seule) : 9 · inatteignable : 0

**Conséquence pour 0025** : les fichiers distincts ne sont PAS de simples doublons — souvent un extrait d'article côté recueil contre le scan du volume entier côté My Library, parfois un meilleur scan côté recueil. Supprimer le groupe sans les **réconcilier au préalable** (rattacher l'URL/fichier recueil à la notice My Library) **détruirait ces fichiers** → **perte d'information, cause de NO-GO** s'ajoutant aux pertes métadonnées de l'audit. Les vrais doublons (hash identique), eux, ne posent pas de perte de fichier. Aucune copie n'est supprimée ici.

## Détail

| Année | Titre | Recueil (o) | My Library (o) | Verdict |
|---|---|---|---|---|
| 1971 | Nouvelles formes de financement de l’action in | — | — | url_manquante |
| 1972 | Environnement et projet de civilisation | 1,063,177 | 27,231,597 | taille_differente |
| 1973 | Développement, environnement et évaluation des | 12,896,420 | 12,896,420 | taille_identique |
| 1973 | Réactions au rapport "The Limits to growth" | 295,834 | 295,834 | taille_identique |
| 1975 | Environnement et politique scientifique | 109,799,028 | 109,799,028 | taille_identique |
| 1976 | De l'effet de domination à la 'self-reliance'  | 19,692,290 | 19,692,290 | taille_identique |
| 1977 | Substitution entre ressources naturelles et no | — | — | url_manquante |
| 1978 | Environnement et développement : de l'external | 26,406,280 | 26,406,280 | taille_identique |
| 1978 | demande énergétique au tiers monde et besoin d | — | — | url_manquante |
| 1979 | Choix énergétiques et choix de société : mythe | 9,545,976 | 9,545,976 | taille_identique |
| 1979 | Energies nouvelles et stratégies des pays en d | 34,762,411 | 34,762,411 | taille_identique |
| 1981 | Progrès techniques et recherche de nouveaux mo | 13,314,245 | 13,314,245 | taille_identique |
| 1982 | Environment and development revisited : ten ye | 17,404,908 | 17,404,908 | taille_identique |
| 1982 | La crise de l'Etat protecteur et l'exercice de | 32,866,873 | 32,866,873 | taille_identique |
| 1982 | Energy, development styles and capital require | — | — | url_manquante |
| 1983 | Le potentiel de développement endogène | 32,596,991 | 32,596,991 | taille_identique |
| 1984 | Developing in harmony with nature : consumptio | 38,925,006 | 38,925,006 | taille_identique |
| 1984 | L'économie cachée en France : état du débat et | 3,285,442 | 3,285,442 | taille_identique |
| 1985 | Trade and development : a prospective view of  | 35,439,360 | 35,439,360 | taille_identique |
| 1985 | Planification décentralisée et modes de dévelo | — | — | url_manquante |
| 1986 | Le nucléaire en France: un projet technique ir | — | — | url_manquante |
| 1989 | Le bouleversement des climats. Comment gérer l | 2,292,822 | 2,292,822 | taille_identique |
| 1991 | Instruments pour une gestion collective des ri | 278,539 | 278,539 | taille_identique |
| 1991 | Politique énergétique et effet de serre. Une e | — | — | url_manquante |
| 1992 | Variables de coordination et négociation, en u | 205,008 | 205,008 | taille_identique |
| 1992 | L'économie, l'écologie et la nature des choses | 161,589 | 161,589 | taille_identique |
| 1992 | Réduire les émissions de gaz à effet de serre  | — | — | url_manquante |
| 1993 | Armements et économie : une nouvelle donne pou | 324,453 | 324,453 | taille_identique |
| 1993 | Sciences et intérêts : la figure de la dénonci | 49,440 | 49,440 | taille_identique |
| 1993 | Politiques de l'environnement et transition ve | 148,113 | 148,113 | taille_identique |
| 1993 | Permis d'émission négociables | — | — | url_manquante |
| 1995 | Trajectoires institutionnelles et choix d'inst | 1,770,559 | 1,770,559 | taille_identique |
| 1996 | Le développement durable et le devenir des vil | 75,610 | 75,610 | taille_identique |
| 1997 | Les permis négociables et la Convention sur le | 182,607 | 182,607 | taille_identique |
| 1997 | Inﬂuence of socioeconomic inertia and uncertai | 213,589 | 213,589 | taille_identique |
| 1997 | Social Decision-Making under Scientific Contro | 225,916 | 225,916 | taille_identique |
| 1997 | Les enjeux des négociations sur le climat De R | 263,651 | 263,651 | taille_identique |
| 1997 | Le concept d'environnement, une hiérarchie enc | 221,031 | 221,031 | taille_identique |
| 1997 | L'ambivalence de la précaution et la transform | 261,561 | 261,561 | taille_identique |
| 1998 | Sustainable development and the process of jus | 103,805 | 103,805 | taille_identique |
| 1998 | L'écodéveloppement revisité | 128,325 | 128,325 | taille_identique |
| 1998 | Annexe 1 LES SCÉNARIOS ÉNERGÉTIQUES DE LA FRAN | 270,894 | 270,894 | taille_identique |

## URL préservées

Les deux URL de chaque paire sont enregistrées dans le JSON (`url_recueil`, `url_mylib`) — donc conservées en versionné même si le groupe Recueil_CIRED venait un jour à être supprimé.

## Reproduire

```bash
uv run python src/compare_recueil_urls.py  # réseau + creds Zotero
```
