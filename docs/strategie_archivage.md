# Stratégie d'archivage CIRED — Note de synthèse

*Date : 2026-05-15*

---

## 1. Cadre juridique

### Loi Lemaire (art. L533-4 Code de la recherche, 7 octobre 2016)

L'article 30 de la loi pour une République Numérique inscrit dans le Code de la recherche (art. L533-4) le droit de l'auteur à diffuser en accès ouvert la version finale de son manuscrit accepté (postprint), même après cession de droits exclusifs à un éditeur, dès lors que la recherche est financée à au moins 50 % par des fonds publics. L'embargo maximal est de **6 mois** pour les STM (sciences, technologies, médecine) et de **12 mois** pour les SHS.

**Point critique pour le CIRED** : la loi s'applique uniquement aux articles soumis **à compter du 9 octobre 2016**. Le corpus archivé (1970–2013) est entièrement antérieur à cette date — la loi Lemaire est donc **pratiquement inapplicable** à cet ensemble. L'archivage de ce fonds doit reposer sur les politiques propres de chaque éditeur (tableau §4) et sur les droits institutionnels détenus par le CIRED/CNRS sur la littérature grise.

### Droits institutionnels

Pour les **documents de travail**, **rapports** et **notes internes** produits par les agents CNRS/EHESS/ENPC, l'employeur dispose de droits patrimoniaux sur les œuvres créées dans le cadre du service (art. L111-1 et L121-7-1 CPI). Ces documents peuvent en principe être déposés dans HAL sous la responsabilité du laboratoire, sans dépendre d'une politique éditeur. Cette règle couvre la majorité du fonds Sachs — voir §5.

### Accord national CNRS–Elsevier

L'accord de licence nationale signé en 2019 prévoit l'import automatique dans HAL des métadonnées et des manuscrits acceptés des articles Elsevier impliquant au moins un auteur affilié à un établissement français. Cet import a été mis en œuvre à partir d'octobre 2021 pour les articles publiés en 2019 et 2020. Pour le corpus CIRED (antérieur à 2013), cet accord ne s'applique pas directement, mais il illustre la voie d'import en lot praticable avec Elsevier pour une période plus récente.

---

## 2. Précédents d'archivage rétrospectif

### Recherche effectuée

Recherches menées sur : CEPREMAP, IDDRI, LATTS, et toute UMR française ayant effectué un dépôt massif rétrospectif dans HAL. Durée : limitée conformément aux instructions.

### Résultats

**Aucun précédent de dépôt massif rétrospectif (pré-2013) documenté publiquement trouvé** pour les laboratoires ciblés.

On note cependant :

- **CEPREMAP** maintient ses working papers (séries "Docweb" et "Couverture Orange") via RePEC, sans dépôt HAL systématique rétrospectif identifié publiquement.
- **Laboratoire AAU-CRESSON** (Grenoble, 2023) : retour d'expérience documenté sur une campagne de dépôt intensif de 116 documents en 6 semaines, via un stagiaire, en utilisant OpenEdition Journals et l'outil OCdHAL (HALUGAthon, UGA, oct.–nov. 2023). C'est le précédent le plus proche trouvé.
- **Pratique générale documentée** (wiki CCSD) : usage de Bib2HAL couplé à Zotero pour l'alimentation rétrospective de collections HAL ; Zotero construit les lots par labo/année/type, exportés en BibTeX, puis importés via Bib2HAL.

**Conclusion** : le dépôt rétrospectif massif est une pratique connue et instrumentée (Bib2HAL, SWORD/TEI), mais les retours d'expérience sur corpus historiques (> 10 ans) restent peu documentés publiquement. Le CIRED aurait potentiellement une contribution à faire à cette pratique.

---

## 3. Workflow HAL batch — aperçu

HAL accepte les imports en lot via plusieurs formats et protocoles, documentés sur [doc.hal.science](https://doc.hal.science) :

- **BibTeX / X2HAL** : outil principal pour import par lot depuis un fichier BibTeX. Le plus accessible pour un travail avec Zotero.
- **RIS** : supporté via les outils de conversion avant import BibTeX.
- **TEI XML** : format natif HAL pour les dépôts SWORD ; permet la transmission simultanée des métadonnées et du fichier plein-texte. Schema disponible sur `api.archives-ouvertes.fr`.
- **SWORD / AtomPub** : protocole d'import programmatique (HTTP POST), utilisé par INRIA et d'autres institutions pour des imports à grande échelle. Nécessite des compétences techniques.

Pour ~740 documents, le workflow recommandé est : Zotero → nettoyage des métadonnées → export BibTeX → import X2HAL, avec ajout manuel des fichiers PDF pour les lots éligibles. La mise en œuvre technique est traitée par le ticket 0005.

---

## 4. Politiques éditeurs — tableau des 10 revues principales

Sources : Sherpa/RoMEO (API v2 non accessible sans clé), pages officielles ScienceDirect, SpringerNature, Taylor & Francis; liste Elsevier d'embargo (`legacyfileshare.elsevier.com/promis_misc/external-embargo-list.pdf`); doc.hal.science/chapitres-ouvrage. Date de vérification : 2026-05-15.

| Revue | Éditeur | ISSN (p) | Politique | Embargo (dépôt public) | Version permise | Source | Date vérif. |
|-------|---------|----------|-----------|------------------------|-----------------|--------|-------------|
| Energy Policy | Elsevier | 0301-4215 | Vert — dépôt postprint autorisé après embargo | **24 mois** | Manuscrit accepté (postprint) | ScienceDirect OA options ; liste embargo Elsevier PDF | 2026-05-15 |
| Ecological Economics | Elsevier | 0921-8009 | Vert — dépôt postprint autorisé après embargo | **24 mois** | Manuscrit accepté (postprint) | ScienceDirect OA options ; liste embargo Elsevier PDF | 2026-05-15 |
| Global Environmental Change | Elsevier | 0959-3780 | Vert — dépôt postprint autorisé après embargo | **36 mois** | Manuscrit accepté (postprint) | Liste embargo Elsevier PDF | 2026-05-15 |
| Climatic Change | Springer Nature | 0165-0009 | Vert — dépôt postprint autorisé après embargo | **12 mois** | Manuscrit accepté (postprint) | Springer Nature journal policies (portfolio Springer hybride/abonnement) | 2026-05-15 |
| Climate Policy | Taylor & Francis | 1469-3062 | Vert — dépôt postprint autorisé après embargo | **12 mois** (STM) ou **18 mois** (SHS) — discipline frontalière, **valeur exacte [non confirmée]** | Manuscrit accepté | T&F Author Services; cost finder T&F non consulté | 2026-05-15 |
| Futuribles | Futuribles International | 0337-307X | [non trouvé] — aucune politique publique open access sur le site ou dans Sherpa/RoMEO | — | — | Site futuribles.com ; Sherpa (non indexé) | 2026-05-15 |
| Natures Sciences Sociétés (NSS) | EDP Sciences | 1240-1307 | **Accès ouvert complet depuis janvier 2020** (CC BY 4.0) — articles antérieurs à 2020 : politique non explicitement publiée | Aucun (pour articles ≥ 2020) | Version éditeur (depuis 2020) | EDP Sciences announcement ; nss-journal.org | 2026-05-15 |
| Revue Tiers Monde | Armand Colin / IEDES | [À vérifier] | [non trouvé] — recommandations auteurs ne mentionnent pas HAL ni l'accès ouvert | — | — | PDF recommandations auteurs RTM ; revues.armand-colin.com | 2026-05-15 |
| L'Harmattan (chapitres/livres) | L'Harmattan | — | Dépôt de la version éditeur autorisé **3 ans après parution** | **3 ans** | Version éditeur | doc.hal.science/chapitres-ouvrage | 2026-05-15 |
| CNRS Éditions (livres/chapitres) | CNRS Éditions | — | [non trouvé] — aucune politique publique open access trouvée | — | — | Recherche web CNRS Editions + HAL | 2026-05-15 |

**Note sur les articles Elsevier et l'accord national** : L'accord Couperin–Elsevier (2019–) prévoit l'import automatique des manuscrits acceptés dans HAL pour les articles impliquant des auteurs français publiés à partir de 2019. Pour le corpus CIRED (antérieur à 2013), les embargos ci-dessus s'appliquent, mais ils sont tous expirés — le dépôt des postprints est donc **immédiatement possible** pour tout article Elsevier du corpus, sous réserve de disposer du fichier postprint.

**Couverture du tableau** : 10/10 revues couvertes (certaines avec données partielles ou non trouvées).

---

## 5. Littérature grise et fonds Sachs

### Définitions HAL

HAL accepte les dépôts de **documents de travail** (`[Report] Research Report`), **rapports** (`[Report] Technical Report`), et **autres** (`[Other]`). Ces types documentaires ne nécessitent pas de politique éditeur — l'auteur ou l'institution déposante certifie avoir le droit de diffuser.

### Fonds Sachs (~386 PDFs, CIR_SAC_, 1970–1998)

Le fonds Sachs constitue de la littérature grise institutionnelle produite dans le cadre de la mission de service public de recherche du CIRED. En tant qu'UMR CNRS/EHESS :

- Les agents CNRS sont fonctionnaires : leurs œuvres de service relèvent du régime de l'art. L111-1 al. 3 CPI — l'État/CNRS détient les droits patrimoniaux.
- Les chercheurs EHESS (EPST) sont dans une situation similaire.
- Les documents sans co-auteur externe et sans contrat éditeur peuvent en principe être déposés dans HAL par le laboratoire.

**[À CONFIRMER avec la direction]** : avant tout dépôt du fonds Sachs, obtenir confirmation de la direction du CIRED et du/de la responsable juridique CNRS sur :
1. La qualification exacte des droits (CNRS vs auteur individuel) pour chaque type de document.
2. L'existence éventuelle de contrats de cession à des éditeurs pour certains documents du fonds.
3. La politique souhaitée concernant les documents impliquant des auteurs extérieurs au CIRED.

### Recommandation pour les WP sans ambiguïté

Les working papers CIRED (série interne, sans contrat éditeur identifié) constituent le sous-ensemble le plus sûr pour un premier dépôt en lot. À traiter en priorité après confirmation de la direction.

---

## 6. Acteurs institutionnels

### Contacts identifiés

| Rôle | Personne | Institution | Statut |
|------|----------|-------------|--------|
| Référente documentation / contact HAL CIRED | **Delphine Du Pasquier** | ENPC, DirDoc | Confirmé (sources ENPC, mention dans documentation CIRED) |
| Pôle Science ouverte ENPC / expert HAL import | **Frédérique Bordignon** | ENPC, DirDoc | Confirmé (HAL cv, publication JNSO 2019) |
| Direction CIRED | **Franck Lecocq** | AgroParisTech / ENPC | Confirmé (sources web CIRED) |
| Direction adjointe CIRED | **Catherine Boemare** | EHESS | Confirmé (sources CIRED AERES) |
| Secrétariat général CIRED | **Naceur Chaabane** | CNRS | Confirmé (sources CIRED AERES) |
| Correspondant HAL CNRS pour l'UMR | [À CONFIRMER] | CNRS INSHS ou DR Île-de-France | Non trouvé publiquement |
| Correspondant science ouverte EHESS | [À CONFIRMER] | EHESS | Non trouvé publiquement |
| Correspondant HAL Cirad (tutelle CIRED) | [À CONFIRMER] | Cirad, DiSCO | Cirad a une délégation à l'information scientifique (DiSCO) — contact à établir |

### Portails HAL existants du CIRED

- Collection principale : [cnrs.hal.science/CIRED](https://cnrs.hal.science/CIRED)
- Collection ENPC : [enpc.hal.science/CIRED](https://enpc.hal.science/CIRED)

**[À CONFIRMER]** : identifier qui administre actuellement ces collections et si elles sont en mode dépôt actif ou archivé.

### Ressources institutionnelles

- **CNRS Science ouverte** : [science-ouverte.cnrs.fr](https://www.science-ouverte.cnrs.fr) — guides, correspondants, politique CNRS HAL obligatoire depuis 2020.
- **Documentation HAL ENPC** : [espacechercheurs.enpc.fr/fr/hal](https://espacechercheurs.enpc.fr/fr/hal) — ressource pertinente pour le CIRED via ENPC.
- **LEESU (UMR voisine ENPC)** : LEESU (181 fichiers) — périmètre à confirmer avec l'auteur, non traité dans cette note.

---

## 7. Recommandations

### 7.1 Périmètre prioritaire

**Tier A — Dépôt immédiat possible (embargo expiré ou inexistant)**

Tous les articles du corpus publiés avant 2013 dans des revues Elsevier (Energy Policy, Ecological Economics, Global Environmental Change) : les embargos de 24–36 mois sont expirés depuis au moins 10 ans. Le dépôt du postprint est immédiatement autorisé, sous réserve de disposer du fichier.

Estimation : ~200–300 articles dans ces trois revues (à affiner depuis l'index JSON ticket 0002).

**Tier B — Dépôt immédiat possible (littérature grise)**

Working papers et rapports internes CIRED sans contrat éditeur identifié, après confirmation des droits par la direction (§5). Le fonds Sachs (386 PDFs) constitue le gisement le plus important.

**Tier C — Dépôt possible après vérification**

- Articles Springer (Climatic Change, embargo 12 mois — expiré pour tout le corpus pré-2013).
- Articles Taylor & Francis (Climate Policy, embargo 12–18 mois — expiré pour tout le corpus pré-2013).
- Chapitres L'Harmattan publiés avant 2023 (embargo 3 ans — expiré pour le corpus pré-2013).
- Articles NSS antérieurs à 2020 : politique non explicitement publiée — vérification directe auprès d'EDP Sciences recommandée.

**Tier D — Action humaine requise avant dépôt**

- Futuribles : contacter l'éditeur pour obtenir une autorisation écrite.
- Armand Colin / Tiers Monde : contacter l'éditeur.
- CNRS Éditions : contacter l'éditeur.
- Fonds Sachs : confirmation juridique direction CIRED + CNRS.

### 7.2 Ordre de dépôt suggéré

1. **Constituer l'index complet** (ticket 0002) avec identification des articles par éditeur, année, et disponibilité du fichier postprint.
2. **Confirmer les droits** sur le fonds Sachs avec la direction (1 réunion suffit).
3. **Premier dépôt pilote** : 20–30 working papers CIRED sans ambiguïté (test du workflow Bib2HAL/X2HAL).
4. **Dépôt en lot Elsevier** : articles Tier A, par ordre chronologique inverse (plus récent d'abord, car postprints plus faciles à retrouver).
5. **Dépôt fonds Sachs** : après feu vert direction, en sous-lots par auteur/année.
6. **Contacts éditeurs** Tier D en parallèle des étapes 3–5.

### 7.3 Points bloquants nécessitant action humaine

| Blocage | Action requise | Priorité |
|---------|---------------|----------|
| Droits fonds Sachs | Réunion direction CIRED + avis juridique CNRS | Haute |
| Politique Futuribles, Armand Colin, CNRS Éditions | Courriel aux éditeurs demandant autorisation expresse | Moyenne |
| Identité administrateur collections HAL CIRED | Contacter Delphine Du Pasquier / ENPC DirDoc | Haute |
| Politique NSS articles pré-2020 | Courriel EDP Sciences | Basse |
| Embargo exact Climate Policy (T&F) | Consulter T&F open access cost finder (URL : authorservices.taylorandfrancis.com) | Basse |
| Correspondants HAL CNRS INSHS et Cirad DiSCO | Contact via portails institutionnels respectifs | Moyenne |
| Disponibilité des fichiers postprint | Enquête auprès des auteurs concernés (en particulier pour articles 1980–1998) | Haute |

---

*Note rédigée sur la base de recherches web effectuées le 2026-05-15. Les politiques éditeurs sont susceptibles d'évoluer ; vérifier les sources indiquées avant tout dépôt effectif.*
