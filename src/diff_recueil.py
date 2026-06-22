"""Diff des corrections d'Antonin entre le groupe Recueil_CIRED et My Library.

Antonin a corrigé des métadonnées dans le groupe privé `Recueil_CIRED`. On veut
importer ces corrections **groupe → perso** (direction unique), mais seulement
après revue humaine — ne jamais écraser sur la seule hypothèse que le groupe est
meilleur (leçon du fonds Sachs).

Ce module fournit la partie *diff de champs*, pure et testable : pour une paire
(notice de groupe, notice perso) déjà appariée, il liste les champs où le groupe
diffère, en distinguant :
  - `ajout`       : le perso est vide, le groupe renseigne → correction sûre ;
  - `modification`: les deux renseignés mais différents → à arbitrer ;
  - le perso renseigné et le groupe vide est **ignoré** (jamais d'effacement).

L'appariement groupe↔perso n'est PAS déterministe (les URL de groupe portent des
noms descriptifs, pas de clé d'archive — c'est ce qui bloquait 0015). Il est
délégué au matcher flou `match_untyped` (issu de 0008) ; voir `main`. Ce module
ne fait aucune écriture Zotero : il produit un rapport pour revue.
"""

import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger("diff_recueil")

DEFAULT_OUTPUT = Path("outputs/recueil_corrections_report.json")
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_GROUP_ID = "2511149"  # groupe privé "Recueil_CIRED"

# Champs où une correction d'Antonin a un sens à importer. On ignore les champs
# techniques (key, version, dateAdded…) et la collection.
DIFFABLE_FIELDS = (
    "title", "publicationTitle", "bookTitle", "publisher", "place",
    "volume", "issue", "pages", "date", "series", "edition", "language",
    "DOI", "ISSN", "ISBN", "abstractNote",
)


def _norm(value: str | None) -> str:
    """Comparaison robuste : espaces normalisés, insensible à la casse."""
    return " ".join((value or "").split()).strip().lower()


def diff_creators(group: list[dict], perso: list[dict]) -> dict | None:
    """Diff des auteurs (liste « Nom, Prénom »), ou None si identiques.

    On compare la séquence normalisée ; toute différence est une `modification`
    à arbitrer (l'ordre et l'orthographe des auteurs comptent).
    """
    def names(cr):
        out = []
        for c in cr or []:
            last, first = c.get("lastName") or "", c.get("firstName") or ""
            out.append(_norm(f"{last} {first}".strip() or (c.get("name") or "")))
        return out
    g, p = names(group), names(perso)
    if g == p:
        return None
    return {"type": "modification", "groupe": g, "perso": p}


def diff_fields(group: dict, perso: dict) -> dict:
    """Champs où le groupe corrige/complète le perso. Sens groupe → perso.

    Retourne {champ: {type, groupe, perso}}. Un champ vide côté groupe n'efface
    jamais le perso (absent du diff).
    """
    out: dict[str, dict] = {}
    for f in DIFFABLE_FIELDS:
        gv, pv = group.get(f) or "", perso.get(f) or ""
        if _norm(gv) == _norm(pv):
            continue
        if not _norm(gv):
            continue  # groupe vide : pas d'effacement
        out[f] = {"type": "ajout" if not _norm(pv) else "modification",
                  "groupe": gv, "perso": pv}
    cre = diff_creators(group.get("creators", []), perso.get("creators", []))
    if cre:
        out["creators"] = cre
    return out


def corrections_report(pairs: list[dict]) -> dict:
    """Rapport de corrections pour une liste de paires appariées.

    Chaque paire : {"groupe": data, "perso": data, "perso_key": str, "score": x}.
    """
    rows, n_ajout, n_modif = [], 0, 0
    for pr in pairs:
        d = diff_fields(pr["groupe"], pr["perso"])
        if not d:
            continue
        n_ajout += sum(1 for v in d.values() if v["type"] == "ajout")
        n_modif += sum(1 for v in d.values() if v["type"] == "modification")
        rows.append({"perso_key": pr.get("perso_key"), "score": pr.get("score"),
                     "titre": pr["perso"].get("title"), "champs": d})
    return {
        "paires_avec_corrections": len(rows),
        "total_ajouts": n_ajout,
        "total_modifications": n_modif,
        "corrections": rows,
    }


def _pair_fuzzy(group_notices, perso_notices, threshold):
    """Apparie groupe→perso par similarité (délégué à match_untyped, 0008).

    Import paresseux : le module `match_untyped` n'arrive sur `main` qu'au merge
    de 0008. Tant qu'il est absent, seules les fonctions de diff (pures) tournent.
    """
    import re
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import match_untyped as mu  # noqa: E402

    def year_of(data):
        m = re.search(r"\b(\d{4})\b", data.get("date") or "")
        return int(m.group(1)) if m else None

    # match_untyped lit `year` ; les notices Zotero portent `date` -> on l'expose.
    perso_pool = [{**p, "year": p.get("year") or year_of(p)} for p in perso_notices]
    pairs = []
    for g in group_notices:
        doc = {"titre": g.get("title"),
               "auteurs": [f"{c.get('lastName','')} {c.get('firstName','')}".strip()
                           for c in g.get("creators", [])],
               "annee": year_of(g)}
        cands = mu.match_one(doc, perso_pool, top=1)
        if cands and cands[0]["score"] >= threshold:
            perso = next(p for p in perso_notices if p.get("key") == cands[0]["key"])
            pairs.append({"groupe": g, "perso": perso,
                          "perso_key": perso.get("key"), "score": cands[0]["score"]})
    return pairs


def _fetch_data(library: str, api_key: str) -> list[dict]:
    """`data` des notices top-level d'une bibliothèque (via reconcile_zotero)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reconcile_zotero as rz  # noqa: E402
    return [it["data"] for it in rz.fetch_top_items(library, api_key)]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--group-notices", type=Path, default=None,
                   help="JSON des `data` de notices du groupe (hors-ligne)")
    p.add_argument("--perso-notices", type=Path, default=None,
                   help="JSON des `data` de notices My Library (hors-ligne)")
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--threshold", type=float, default=0.75)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.group_notices and args.perso_notices:
        group = json.loads(args.group_notices.read_text())
        perso = json.loads(args.perso_notices.read_text())
    else:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import reconcile_zotero as rz  # noqa: E402
        env = rz.load_env(args.env)
        api_key = env["ZOTERO_API_KEY"]
        group = _fetch_data(f"groups/{args.group_id}", api_key)
        perso = _fetch_data(f"users/{rz.fetch_user_id(api_key)}", api_key)
    pairs = _pair_fuzzy(group, perso, args.threshold)
    report = corrections_report(pairs)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    logger.info("Paires appariées          : %d", len(pairs))
    logger.info("  avec corrections         : %d", report["paires_avec_corrections"])
    logger.info("  ajouts / modifications   : %d / %d",
                report["total_ajouts"], report["total_modifications"])
    logger.info("Rapport (à revoir) écrit : %s", args.output)


if __name__ == "__main__":
    main()
