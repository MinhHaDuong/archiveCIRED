"""Apparier les docs sans clé d'archive aux notices Zotero (titre/auteur/année).

195 documents de `doc_index.json` n'ont aucune clé d'archive joignable
(`type=null` pour la plupart) : ni nom `CIR_/ENPC`, ni id `YYYY-NNN`. On ne peut
donc pas les réconcilier par identifiant comme le fait `reconcile_zotero.py`. Ce
script les rapproche des notices Zotero par **appariement flou** titre + nom
d'auteur + année, et partitionne :

  - `probable`   : un candidat à score élevé — « déjà dans Zotero sous un autre
                   nom », à **confirmer par un humain** ;
  - `incertain`  : candidat à score moyen — à arbitrer ;
  - `absent`     : aucun candidat crédible — « vraiment absent du catalogue » ;
  - `sans_metadonnees` : titre/auteur/année trop pauvres pour décider.

Règle projet : on apparie par id, **jamais** par titre pour *fusionner*. Ici le
titre ne sert qu'à *suggérer* ; rien n'est écrit dans Zotero. Cela évite de
rejouer les faux doublons du fonds Sachs.

Sans réseau, les fonctions de scoring sont pures et testables. La collecte des
notices (titre/auteurs/date) réutilise la lib standard via `reconcile_zotero`.
"""

import argparse
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("match_untyped")

DEFAULT_DOC_INDEX = Path("outputs/doc_index.json")
DEFAULT_NOTICES = Path("outputs/zotero_notices.json")
DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_GROUP_ID = rz.DEFAULT_GROUP_ID
DEFAULT_REPORT = Path("outputs/match_untyped_report.json")

# Mots vides FR/EN à retirer des titres avant comparaison par jetons.
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "d", "l", "et", "ou",
    "a", "au", "aux", "en", "dans", "pour", "par", "sur", "the", "of", "and",
    "to", "in", "for", "on", "an",
}


def normalize(text: str | None) -> str:
    """Minuscule, sans accents ni ponctuation, espaces normalisés.

    Ne retire pas les mots vides ni les jetons courts — c'est le rôle de
    `_tokens`. L'apostrophe est traitée comme une coupure (« l'eau » -> « l eau »).

    >>> normalize("L'Environnement, Obstacle ?")
    'l environnement obstacle'
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return " ".join(ascii_text.split())


def _tokens(text: str | None) -> set[str]:
    """Jetons significatifs d'un texte normalisé (mots vides retirés)."""
    return {t for t in normalize(text).split() if t not in STOPWORDS and len(t) > 1}


def last_names(authors: list[str] | None) -> set[str]:
    """Noms de famille normalisés extraits d'une liste d'auteurs.

    Heuristique : si une virgule est présente, le nom précède (« Godard,
    Olivier ») ; sinon on prend le premier jeton (« Hourcade J.-C. »).

    >>> sorted(last_names(["Godard, Olivier", "Hourcade J.-C."]))
    ['godard', 'hourcade']
    """
    if not authors:
        return set()
    names = set()
    for a in authors:
        if not a:
            continue
        head = a.split(",")[0] if "," in a else a.split()[0] if a.split() else a
        n = normalize(head)
        if n:
            names.add(n.split()[0])
    return names


def title_sim(a: str | None, b: str | None) -> float:
    """Similarité de Jaccard sur jetons de titre, dans [0, 1].

    >>> title_sim("gestion de l'eau", "la gestion de l eau") > 0.7
    True
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _title_metrics(a: str | None, b: str | None) -> tuple[float, float]:
    """Retourne (jaccard, containment) pour deux titres.

    containment = 0 si le plus court a moins de 4 jetons significatifs.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0, 0.0
    inter = len(ta & tb)
    jac = inter / len(ta | tb)
    smaller = min(len(ta), len(tb))
    cov = inter / smaller if smaller >= 4 else 0.0
    return jac, cov


def title_match(a: str | None, b: str | None) -> float:
    """Accroche de titre robuste à la troncature, dans [0, 1].

    Maximum du Jaccard et d'un coefficient de *containment* (intersection sur le
    plus petit ensemble). Le containment rattrape le cas fréquent où le titre du
    doc est une troncature du titre complet de la notice — mais il n'est activé
    que si le plus court a au moins 4 jetons significatifs, faute de quoi deux
    titres courts partageant des mots génériques (« développement durable »)
    seraient faussement appariés.

    >>> title_match("gestion eau pays mediterraneens",
    ...             "elements gestion eau pays mediterraneens approche") == 1.0
    True
    """
    jac, cov = _title_metrics(a, b)
    return max(jac, cov)


def _notice_lastnames(notice: dict) -> set[str]:
    """Noms de famille des creators d'une notice Zotero."""
    names = set()
    for c in notice.get("creators", []) or []:
        ln = c.get("lastName") or c.get("name") or ""
        n = normalize(ln)
        if n:
            names.add(n.split()[0])
    return names


def score(doc: dict, notice: dict) -> float:
    """Score d'appariement doc(index) ↔ notice(Zotero), dans [0, 1].

    Le titre est le signal fiable et porte le score. L'année et les noms
    d'auteur ne sont que des **bonus additifs** : les champs auteur sont
    bruités côté doc (noms de revue, prénoms pris pour patronymes), donc ils ne
    doivent jamais *abaisser* un bon appariement de titre. Aucun bonus n'est
    accordé sans une accroche de titre minimale, pour écarter les faux positifs
    « même année, titre différent ».

    Exception : quand l'accroche de titre vient *essentiellement* du containment
    (jac < 0.4, le plus court est sous-ensemble d'un titre beaucoup plus long),
    une corroboration auteur OU année est exigée pour rester « probable ». Sans
    elle, le score est plafonné à 0.74 (incertain). Cela prévient les faux
    positifs du type Godard↔Hourcade (cov=0.75, jac=0.25, auteurs/années
    différents).
    """
    jac, cov = _title_metrics(doc.get("titre"), notice.get("title"))
    t = max(jac, cov)
    if t < 0.2:
        return round(t, 4)
    da, na = last_names(doc.get("auteurs")), _notice_lastnames(notice)
    author = 1.0 if (da & na) else 0.0
    dy, ny = doc.get("annee"), notice.get("year")
    year = 1.0 if (dy and ny and int(dy) == int(ny)) else 0.0
    raw = t + 0.12 * year + 0.10 * author
    if cov > 0 and jac < 0.4 and not (author or year):
        return round(min(0.74, raw), 4)
    return round(min(1.0, raw), 4)


def match_one(doc: dict, notices: list[dict], top: int = 3) -> list[dict]:
    """Meilleurs candidats Zotero pour un doc, triés par score décroissant."""
    scored = (
        {"key": n.get("key"), "title": n.get("title"), "year": n.get("year"),
         "score": score(doc, n)}
        for n in notices
    )
    ranked = sorted(scored, key=lambda c: c["score"], reverse=True)
    return ranked[:top]


def _has_metadata(doc: dict) -> bool:
    """Le doc a-t-il de quoi être apparié ? (titre exploitable + année OU auteur)"""
    return bool(_tokens(doc.get("titre")) and (doc.get("annee") or doc.get("auteurs")))


def match_all(docs: list[dict], notices: list[dict],
              probable: float = 0.75, maybe: float = 0.5) -> dict:
    """Partitionne les docs en probable / incertain / absent / sans_metadonnees."""
    out = {"total": len(docs), "probable": [], "incertain": [],
           "absent": [], "sans_metadonnees": []}
    for doc in docs:
        if not _has_metadata(doc):
            out["sans_metadonnees"].append(doc["id"])
            continue
        cands = match_one(doc, notices)
        best = cands[0]["score"] if cands else 0.0
        row = {"doc_id": doc["id"], "titre": doc.get("titre"),
               "annee": doc.get("annee"), "auteurs": doc.get("auteurs"),
               "candidats": cands}
        if best >= probable:
            out["probable"].append(row)
        elif best >= maybe:
            out["incertain"].append(row)
        else:
            out["absent"].append(doc["id"])
    return out


# --- collecte des notices Zotero (réseau) -------------------------------------

def notice_of(item: dict) -> dict:
    """Réduit une notice Zotero brute aux champs utiles à l'appariement."""
    d = item.get("data", {})
    date = d.get("date") or ""
    m = re.search(r"\b(\d{4})\b", date)
    return {
        "key": d.get("key"),
        "title": d.get("title"),
        "year": int(m.group(1)) if m else None,
        "creators": [{"lastName": c.get("lastName"), "name": c.get("name")}
                     for c in d.get("creators", []) or []],
    }


def collect_notices(env_path: Path, group_id: str) -> list[dict]:
    """Notices perso + groupe, réduites aux champs d'appariement."""
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    user_id = rz.fetch_user_id(api_key)
    perso = rz.fetch_top_items(f"users/{user_id}", api_key)
    groupe = rz.fetch_top_items(f"groups/{group_id}", api_key)
    return [notice_of(it) for it in perso + groupe]


def untyped_docs(docs: list[dict]) -> list[dict]:
    """Docs sans aucune clé d'archive joignable (cf. reconcile_zotero.doc_keys)."""
    return [d for d in docs if not rz.doc_keys(d)]


def render_markdown(report: dict) -> str:
    """Rapport lisible : suggestions à confirmer + liste consolidée des absents."""
    lines = [
        "# Appariement des docs sans clé d'archive ↔ Zotero",
        "",
        f"- Docs sans clé d'archive : **{report['total']}**",
        f"- Probable (déjà dans Zotero, à confirmer) : **{len(report['probable'])}**",
        f"- Incertain (à arbitrer, bruit de vocabulaire générique) : "
        f"**{len(report['incertain'])}**",
        f"- Absent (aucun candidat crédible) : **{len(report['absent'])}**",
        f"- Sans métadonnées exploitables (cf. OCR, ticket 0006) : "
        f"**{len(report['sans_metadonnees'])}**",
        "",
        "## Probable — à confirmer puis fusionner (groupe → perso), pas ajouter",
        "",
    ]
    for m in report["probable"]:
        c = m["candidats"][0]
        lines.append(f"- `{m['doc_id']}` [{m['annee']}] {m['titre']!r}")
        lines.append(f"  - → Zotero `{c['key']}` ({c['score']:.2f}) {c['title']!r}")
    lines += ["", "## Incertain — à arbitrer (score 0.5–0.75)", ""]
    for m in report["incertain"]:
        c = m["candidats"][0]
        lines.append(f"- `{m['doc_id']}` [{m['annee']}] {(m['titre'] or '')!r} "
                     f"→ {c['score']:.2f} {(c['title'] or '')!r}")
    lines += ["", "## Absent — liste consolidée des documents réellement absents", ""]
    lines += [f"- `{doc_id}`" for doc_id in report["absent"]]
    lines += ["", "## Sans métadonnées — indécidables sans OCR/saisie", ""]
    lines += [f"- `{doc_id}`" for doc_id in report["sans_metadonnees"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--doc-index", type=Path, default=DEFAULT_DOC_INDEX)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--notices", type=Path, default=DEFAULT_NOTICES,
                   help="JSON de notices déjà collectées (hors-ligne, sans réseau)")
    p.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--probable", type=float, default=0.75)
    p.add_argument("--maybe", type=float, default=0.5)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    docs = untyped_docs(json.loads(args.doc_index.read_text()))
    if args.notices.exists():
        notices = json.loads(args.notices.read_text())
        logger.info("Notices chargées (cache) : %d", len(notices))
    else:
        notices = collect_notices(args.env, args.group_id)
        args.notices.write_text(json.dumps(notices, ensure_ascii=False, indent=2))
        logger.info("Notices collectées et mises en cache : %d", len(notices))

    report = match_all(docs, notices, args.probable, args.maybe)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    args.output.with_suffix(".md").write_text(render_markdown(report))

    logger.info("Docs sans clé          : %d", report["total"])
    logger.info("  probable (à confirmer): %d", len(report["probable"]))
    logger.info("  incertain (à arbitrer): %d", len(report["incertain"]))
    logger.info("  absent (à ajouter)    : %d", len(report["absent"]))
    logger.info("  sans métadonnées      : %d", len(report["sans_metadonnees"]))
    logger.info("Rapport écrit : %s", args.output)


if __name__ == "__main__":
    main()
