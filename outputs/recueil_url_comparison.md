# Comparaison des URL « recueil non dupliquée » (54 paires)

Généré par `src/compare_recueil_urls.py`. Données : `recueil_url_comparison.json`. **Lecture seule, aucune décision.**

Chaque notice du groupe Recueil_CIRED pointe une URL inari ; My Library porte un document équivalent sous **une autre URL inari** (deux buckets distincts). On compare les deux fichiers, sans en supprimer aucun.

## Synthèse

- **Fichiers distincts** (taille différente, ou SHA-256 différent) : **14**
- Vrais doublons (SHA-256 identiques) : **31** sur 31 de taille égale
- Sans PDF des deux côtés (métadonnée seule) : 9 · inatteignable : 0

**Conséquence pour 0025** : les fichiers distincts ne sont PAS de simples doublons — souvent un extrait d'article côté recueil contre le scan du volume entier côté My Library, parfois un meilleur scan côté recueil. Supprimer le groupe sans les **réconcilier au préalable** (rattacher l'URL/fichier recueil à la notice My Library) **détruirait ces fichiers** → **perte d'information, cause de NO-GO** s'ajoutant aux pertes métadonnées de l'audit. Les vrais doublons (hash identique), eux, ne posent pas de perte de fichier. Aucune copie n'est supprimée ici.

## Détail

| Année | Titre | Recueil (o) | My Library (o) | Verdict |
|---|---|---|---|---|
| 1971 | Nouvelles formes de financement de l’action in | — | — | url_manquante |
| 1973 | Développement, environnement et évaluation des | 12,896,420 | 12,896,420 | identique (hash) |
| 1973 | Réactions au rapport "The Limits to growth" | 295,834 | 295,834 | identique (hash) |
| 1975 | La politique de l'environnement et l'avenir de | 7,038,352 | 6,881,391 | taille_differente |
| 1975 | L’environnement, obstacle ou argument pour un  | 3,291,267 | 3,286,554 | taille_differente |
| 1975 | L'occupation  des espaces littoraux méditérran | 3,395,438 | 3,450,889 | taille_differente |
| 1975 | Environnement et politique scientifique | 109,799,028 | 109,799,028 | identique (hash) |
| 1976 | De l'effet de domination à la 'self-reliance'  | 19,692,290 | 19,692,290 | identique (hash) |
| 1977 | Substitution entre ressources naturelles et no | — | — | url_manquante |
| 1978 | Développement, utopie, projet de société | 1,167,535 | 40,345,467 | taille_differente |
| 1978 | Environnement et développement : de l'external | 26,406,280 | 26,406,280 | identique (hash) |
| 1978 | demande énergétique au tiers monde et besoin d | — | — | url_manquante |
| 1979 | Choix énergétiques et choix de société : mythe | 9,545,976 | 9,545,976 | identique (hash) |
| 1979 | Energies nouvelles et stratégies des pays en d | 34,762,411 | 34,762,411 | identique (hash) |
| 1980 | Les temps - espaces du développement | 27,140,718 | 20,930,129 | taille_differente |
| 1981 | Oppositions locales à des projets d'équipement | 1,733,938 | 34,645,400 | taille_differente |
| 1981 | Plaidoyer pour développer des technologies plu | 827,444 | 13,697,009 | taille_differente |
| 1981 | Progrès techniques et recherche de nouveaux mo | 13,314,245 | 13,314,245 | identique (hash) |
| 1982 | Environment and development revisited : ten ye | 17,404,908 | 17,404,908 | identique (hash) |
| 1982 | Les bifurcations de la politique énergétique f | 1,251,213 | 23,482,808 | taille_differente |
| 1982 | La crise de l'Etat protecteur et l'exercice de | 32,866,873 | 32,866,873 | identique (hash) |
| 1982 | Décentralisation et planification du développe | 2,133,485 | 87,179 | taille_differente |
| 1982 | Energy, development styles and capital require | — | — | url_manquante |
| 1983 | Le potentiel de développement endogène | 32,596,991 | 32,596,991 | identique (hash) |
| 1984 | Developing in harmony with nature : consumptio | 38,925,006 | 38,925,006 | identique (hash) |
| 1984 | Le biais mimétique dans le choix de techniques | 1,137,107 | 20,160,122 | taille_differente |
| 1984 | L'économie cachée en France : état du débat et | 3,285,442 | 3,285,442 | identique (hash) |
| 1985 | Trade and development : a prospective view of  | 35,439,360 | 35,439,360 | identique (hash) |
| 1985 | Planification décentralisée et modes de dévelo | — | — | url_manquante |
| 1986 | Le nucléaire en France: un projet technique ir | — | — | url_manquante |
| 1989 | Le bouleversement des climats. Comment gérer l | 2,292,822 | 2,292,822 | identique (hash) |
| 1989 | Jeux de nature : quand le débat sur l'efficaci | 229,022 | 202,055 | taille_differente |
| 1989 | Développement des réseaux et modulations spati | 2,489,371 | 2,485,646 | taille_differente |
| 1990 | Environnement, modes de coordination et systèm | 2,443,423 | 978,013 | taille_differente |
| 1991 | Instruments pour une gestion collective des ri | 278,539 | 278,539 | identique (hash) |
| 1991 | Politique énergétique et effet de serre. Une e | — | — | url_manquante |
| 1992 | Variables de coordination et négociation, en u | 205,008 | 205,008 | identique (hash) |
| 1992 | L'économie, l'écologie et la nature des choses | 161,589 | 161,589 | identique (hash) |
| 1992 | La relation interdisciplinaire : problèmes et  | 386,184 | 68,823,490 | taille_differente |
| 1992 | Réduire les émissions de gaz à effet de serre  | — | — | url_manquante |
| 1993 | Armements et économie : une nouvelle donne pou | 324,453 | 324,453 | identique (hash) |
| 1993 | Sciences et intérêts : la figure de la dénonci | 49,440 | 49,440 | identique (hash) |
| 1993 | Politiques de l'environnement et transition ve | 148,113 | 148,113 | identique (hash) |
| 1993 | Permis d'émission négociables | — | — | url_manquante |
| 1995 | Trajectoires institutionnelles et choix d'inst | 1,770,559 | 1,770,559 | identique (hash) |
| 1997 | Les permis négociables et la Convention sur le | 182,607 | 182,607 | identique (hash) |
| 1997 | Inﬂuence of socioeconomic inertia and uncertai | 213,589 | 213,589 | identique (hash) |
| 1997 | Social Decision-Making under Scientific Contro | 225,916 | 225,916 | identique (hash) |
| 1997 | Les enjeux des négociations sur le climat De R | 263,651 | 263,651 | identique (hash) |
| 1997 | Le concept d'environnement, une hiérarchie enc | 221,031 | 221,031 | identique (hash) |
| 1997 | L'ambivalence de la précaution et la transform | 261,561 | 261,561 | identique (hash) |
| 1998 | Sustainable development and the process of jus | 103,805 | 103,805 | identique (hash) |
| 1998 | L'écodéveloppement revisité | 128,325 | 128,325 | identique (hash) |
| 1998 | Annexe 1 LES SCÉNARIOS ÉNERGÉTIQUES DE LA FRAN | 270,894 | 270,894 | identique (hash) |

## URL préservées

Les deux URL de chaque paire sont enregistrées dans le JSON (`url_recueil`, `url_mylib`) — donc conservées en versionné même si le groupe Recueil_CIRED venait un jour à être supprimé.

## Reproduire

```bash
uv run python src/compare_recueil_urls.py  # réseau + creds Zotero
```
