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
import re
from pathlib import Path

logger = logging.getLogger("diff_recueil")

DEFAULT_OUTPUT = Path("outputs/recueil_corrections_report.json")
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_GROUP_ID = "2511149"  # groupe privé "Recueil_CIRED"
# En dessous de ce seuil de similarité de titre, l'appariement est tenu pour
# douteux (probablement deux documents différents) et écarté de l'application.
MATCH_TITRE_SAIN = 0.85

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


def _iso_date(value: str | None) -> str:
    """Normalise une date `MM/YYYY` ou `DD/MM/YYYY` en ISO (`YYYY-MM[-DD]`).

    >>> _iso_date("07/1994")
    '1994-07'
    """
    s = " ".join((value or "").split())
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return value or ""


def _field_note(champ: str, gv: str, pv: str,
                journaux: set[str] = frozenset()) -> str | None:
    """Signale une valeur proposée à nettoyer à la main (pas d'import aveugle)."""
    notes = []
    for tok in str(gv).split():
        letters = [c for c in tok if c.isalpha()]
        if len(letters) >= 4 and all(c.upper() == c and c.upper() != c.lower()
                                     for c in letters):
            notes.append("recasser (ALLCAPS)")
            break
    if champ == "bookTitle" and re.search(
            r"(Éditions|Editions|Presses?|Press|Publishers?)\b", str(gv)):
        notes.append("extraire lieu/éditeur du bookTitle")
    if (champ == "volume" and re.search(r"vol", str(pv), re.I)
            and re.fullmatch(r"\d+", str(gv).strip())):
        notes.append("vérifier volume vs numéro (perte d'info ?)")
    if champ == "publisher" and _norm(gv) in journaux:
        notes.append("éditeur = nom de la revue ? préciser l'organisme")
    return " ; ".join(notes) or None


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
    titres = {_norm(group.get("title")), _norm(perso.get("title"))}
    journaux = {_norm(group.get("publicationTitle")),
                _norm(perso.get("publicationTitle"))} - {""}
    for f in DIFFABLE_FIELDS:
        gv, pv = group.get(f) or "", perso.get(f) or ""
        if f == "date":
            gv = _iso_date(gv)  # 07/1994 -> 1994-07
        if _norm(gv) == _norm(pv):
            continue
        if not _norm(gv):
            continue  # groupe vide : pas d'effacement
        # Erreur de saisie fréquente du groupe : le titre de l'article recopié
        # dans publicationTitle. Ne pas écraser la vraie revue du perso.
        if f == "publicationTitle" and _norm(gv) in titres:
            continue
        entry = {"type": "ajout" if not _norm(pv) else "modification",
                 "groupe": gv, "perso": pv}
        note = _field_note(f, gv, pv, journaux)
        if note:
            entry["note"] = note
        out[f] = entry
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
                     "titre_sim": pr.get("titre_sim"),
                     "titre": pr["perso"].get("title"), "champs": d})
    n_douteux = sum(1 for r in rows if (r.get("titre_sim") or 0) < MATCH_TITRE_SAIN)
    return {
        "paires_avec_corrections": len(rows),
        "paires_appariement_douteux": n_douteux,
        "total_ajouts": n_ajout,
        "total_modifications": n_modif,
        "corrections": rows,
    }


def _cell(value) -> str:
    """Valeur de champ en texte de cellule Markdown (listes jointes, pipes échappés)."""
    if isinstance(value, list):
        value = " ; ".join(str(v) for v in value)
    text = " ".join(str(value or "—").split())
    text = text.replace("|", "\\|")
    return text if len(text) <= 90 else text[:87] + "…"


_TABLE_HEAD = [
    "| # | Notice | Champ | Type | Valeur actuelle (My Library) "
    "| Valeur d'Antonin (Recueil_CIRED) | Note |",
    "|--:|--------|-------|------|------------------------------"
    "|----------------------------------|------|",
]


def _table(rows: list[dict], start: int) -> tuple[list[str], int]:
    """Lignes Markdown pour des rows ; renvoie (lignes, prochain numéro)."""
    out, i = [], start
    for row in sorted(rows, key=lambda r: -(r.get("score") or 0)):
        titre = _cell(row.get("titre"))
        for champ, d in row["champs"].items():
            i += 1
            mark = "➕" if d["type"] == "ajout" else "✏️"
            out.append(f"| {i} | {titre} | `{champ}` | {mark} {d['type']} | "
                       f"{_cell(d['perso'])} | {_cell(d['groupe'])} | "
                       f"{d.get('note') or ''} |")
    return out, i


def render_markdown(report: dict) -> str:
    """Deux tables : appariements sûrs (à appliquer) et douteux (à confirmer)."""
    corr = report["corrections"]
    sains = [r for r in corr if (r.get("titre_sim") or 0) >= MATCH_TITRE_SAIN]
    douteux = [r for r in corr if (r.get("titre_sim") or 0) < MATCH_TITRE_SAIN]
    head = [
        "# Corrections d'Antonin à revoir",
        "",
        f"{report['paires_avec_corrections']} notices · "
        f"{report['total_ajouts']} ajouts · {report['total_modifications']} "
        f"modifications · {len(douteux)} appariement(s) douteux.",
        "",
        "Antonin a corrigé les métadonnées dans le **groupe Recueil_CIRED** ; on "
        "reporte ces corrections dans **My Library**. Sens : Recueil_CIRED → My "
        "Library ; la colonne « Valeur d'Antonin » est la valeur *proposée*. "
        "Appariement un-à-un ; dates normalisées ISO ; un `publicationTitle` qui "
        "recopiait le titre est écarté. La colonne **Note** signale ce qui reste "
        "à nettoyer à la main.",
        "",
        "## Appariement sûr (titre concordant) — à appliquer après revue",
        "",
        *_TABLE_HEAD,
    ]
    body, i = _table(sains, 0)
    tail = [
        "",
        "## ⚠️ Appariement douteux — vérifier que c'est le même document",
        "",
        "Titre nettement différent entre les deux notices : probablement deux "
        "documents distincts. **Ne pas appliquer sans vérifier** (PDF, DOI).",
        "",
        *_TABLE_HEAD,
    ]
    body2, _ = _table(douteux, i)
    return "\n".join(head + body + tail + body2) + "\n"


def _pair_fuzzy(group_notices, perso_notices, threshold):
    """Apparie groupe→perso par similarité, en **un-à-un** (délégué à match_untyped).

    Chaque notice de groupe choisit sa meilleure perso ; mais une même perso peut
    être convoitée par plusieurs notices de groupe (le vrai partenaire de l'une
    est absent ou sous le seuil, elle se rabat sur une perso déjà prise). On
    résout en attribuant chaque perso à la notice de groupe au **titre le plus
    proche** (`titre_sim`) ; les prétendantes perdantes sont écartées — c'était
    la source des faux appariements. `titre_sim` est conservé pour partitionner
    sûr / douteux.

    Import paresseux : `match_untyped` n'arrive sur `main` qu'au merge de 0008.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import match_untyped as mu  # noqa: E402

    def year_of(data):
        m = re.search(r"\b(\d{4})\b", data.get("date") or "")
        return int(m.group(1)) if m else None

    # match_untyped lit `year` ; les notices Zotero portent `date` -> on l'expose.
    perso_pool = [{**p, "year": p.get("year") or year_of(p)} for p in perso_notices]
    by_key = {p.get("key"): p for p in perso_notices}

    best: dict[str, dict] = {}  # perso_key -> meilleure paire (titre_sim max)
    for g in group_notices:
        doc = {"titre": g.get("title"),
               "auteurs": [f"{c.get('lastName','')} {c.get('firstName','')}".strip()
                           for c in g.get("creators", [])],
               "annee": year_of(g)}
        cands = mu.match_one(doc, perso_pool, top=1)
        if not cands or cands[0]["score"] < threshold:
            continue
        pk = cands[0]["key"]
        perso = by_key[pk]
        ts = round(mu.title_match(g.get("title"), perso.get("title")), 3)
        if pk not in best or ts > best[pk]["titre_sim"]:
            best[pk] = {"groupe": g, "perso": perso, "perso_key": pk,
                        "score": cands[0]["score"], "titre_sim": ts}
    return list(best.values())


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
    args.output.with_suffix(".md").write_text(render_markdown(report))

    logger.info("Paires appariées          : %d", len(pairs))
    logger.info("  avec corrections         : %d", report["paires_avec_corrections"])
    logger.info("  ajouts / modifications   : %d / %d",
                report["total_ajouts"], report["total_modifications"])
    logger.info("Rapport (à revoir) écrit : %s", args.output)


if __name__ == "__main__":
    main()
