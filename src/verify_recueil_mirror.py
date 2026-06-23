"""Audit indépendant : aucune information perdue si l'on supprime le groupe
Zotero `Recueil_CIRED` (ticket 0025) ?

Vérificateur FRAIS, lecture seule. Le verdict part de l'état en ligne (les 131
notices du groupe + toutes les notices de My Library, pièces jointes incluses) et
ne fait confiance à aucun appariement produit par l'agent qui a peuplé la
collection.

Modèle de couverture (par notice de groupe), du plus fort au plus faible :

  url_preserved  — la même URL/PDF du recueil est présente quelque part dans My
                   Library (notice ou pièce jointe). Préservation triviale.
  doc_equivalent — pas la même URL, mais il existe une notice My Library qui
                   (a) couvre tous les champs énumérés du groupe, (b) corrobore
                   titre + année + au moins les auteurs du groupe, et (c) conserve
                   un PDF/URL si le groupe en a un. La version d'Antonin n'est pas
                   perdue ; seule l'URL redondante du recueil n'est pas dupliquée.
  loss           — ni l'un ni l'autre : soit aucune notice ne correspond, soit la
                   notice trouvée n'a pas de PDF alors que le groupe en porte un,
                   soit un champ énuméré du groupe manque.

Un second axe, indépendant : les **notes** d'annotation rattachées aux notices de
groupe (commentaires d'Antonin) doivent aussi se retrouver dans My Library. Une
note de groupe dont le texte est introuvable côté perso est une perte.

Verdict : go (suppression possible) ssi métadonnées/PDF ET notes sont toutes
préservées (aucune perte sur l'un ou l'autre axe) ; sinon no-go.

La collecte réseau s'appuie sur les helpers lecture seule de `reconcile_zotero`.
Les fonctions de décision (`assess_item`, `assess_all`) sont pures et testées sur
fixtures, sans aucune écriture Zotero.
"""

import argparse
import json
import logging
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("verify_recueil_mirror")

DEFAULT_GROUP_ID = "2511149"  # groupe privé "Recueil_CIRED"
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_REPORT_JSON = Path("outputs/verify_recueil_mirror_report.json")
DEFAULT_REPORT_MD = Path("outputs/verify_recueil_mirror_report.md")

# Champs de métadonnées énumérés par le ticket (hors titre/auteurs/année, qui
# servent à l'appariement). Une notice candidate doit tous les couvrir.
ENUM_FIELDS = ["DOI", "ISSN", "volume", "issue", "pages",
               "publicationTitle", "publisher", "place", "series"]


# --- normalisation (pur) -----------------------------------------------------

def norm_text(s: str | None) -> str:
    """Minuscule, sans accents, ponctuation -> espace, espaces compactés."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def norm_year(date: str | None) -> str:
    """Première année à 4 chiffres d'une date Zotero (souvent `YYYY-MM-DD`)."""
    m = re.search(r"\d{4}", date or "")
    return m.group(0) if m else ""


def author_lastnames(creators: list[dict] | None) -> set[str]:
    """Noms de famille normalisés (ou `name` pour les auteurs corporatifs)."""
    out = set()
    for c in creators or []:
        out.add(norm_text(c.get("lastName") or c.get("name") or ""))
    return out - {""}


def url_basename(url: str | None) -> str:
    """Basename d'URL décodé en minuscules (clé de jointure PDF inari)."""
    if not url:
        return ""
    return urllib.parse.unquote(url).strip().lower().rsplit("/", 1)[-1]


def metadata_missing(group: dict, lib: dict,
                     fields: list[str] = ENUM_FIELDS) -> list[str]:
    """Champs énumérés présents dans `group` mais non couverts par `lib`.

    Couverture par inclusion normalisée bidirectionnelle : « 22 » couvre « 22 »,
    « pp. 29-35 » couvre « 29-35 ». Tolérant exprès — l'objectif est de repérer
    une *vraie* perte (champ absent), pas une divergence de formatage.
    """
    miss = []
    for f in fields:
        gv = norm_text(group.get(f))
        if not gv:
            continue
        lv = norm_text(lib.get(f))
        if not lv or (gv not in lv and lv not in gv):
            miss.append(f)
    return miss


def note_text(html: str | None) -> str:
    """Texte brut d'une note Zotero (HTML retiré, espaces compactés)."""
    if not html:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def unpreserved_notes(group_notes: list[dict],
                      lib_note_texts: list[str]) -> list[dict]:
    """Notes d'annotation du groupe dont le texte est absent de My Library.

    Comparaison par préfixe normalisé (les 60 premiers caractères) : robuste aux
    reformatages HTML mais sensible à une vraie disparition de contenu. Une note
    vide n'est jamais une perte.
    """
    corpus = " || ".join(norm_text(t) for t in lib_note_texts)
    lost = []
    for n in group_notes:
        txt = note_text(n.get("note"))
        if not txt:
            continue
        probe = norm_text(txt)[:60]
        if probe and probe not in corpus:
            lost.append({"parent": n.get("parentItem"),
                         "extrait": txt[:120]})
    return lost


# --- décision (pur) ----------------------------------------------------------

def _title_author_year_match(group: dict, lib: dict) -> bool:
    """Même titre normalisé + même année + auteurs du groupe ⊆ auteurs lib.

    Jamais par titre seul : l'année et les auteurs corroborent l'identité (la
    réutilisation de titres dans le fonds Sachs rendrait l'appariement faux).
    """
    if norm_text(group.get("title")) != norm_text(lib.get("title")):
        return False
    if norm_year(group.get("date")) != norm_year(lib.get("date")):
        return False
    gn = author_lastnames(group.get("creators"))
    return not gn or gn <= author_lastnames(lib.get("creators"))


def assess_item(group: dict, enriched_lib: list[tuple[dict, set[str]]]) -> dict:
    """Niveau de préservation d'une notice de groupe (fonction pure).

    `enriched_lib` : liste de (data My Library, basenames d'URL de la notice et de
    ses pièces jointes). Retourne un dict sérialisable avec `tier` ∈
    {url_preserved, doc_equivalent, loss}, et pour une perte la `reason` et les
    champs `missing`.
    """
    base = {
        "key": group.get("key"),
        "title": group.get("title"),
        "annee": norm_year(group.get("date")),
        "url_basename": url_basename(group.get("url")),
    }
    gub = base["url_basename"]

    # 1. La même URL/PDF du recueil existe-t-elle dans My Library ?
    if gub:
        for lib, ubs in enriched_lib:
            if gub in ubs:
                return {**base, "tier": "url_preserved", "matched": lib.get("key")}

    # 2. Une notice corroborée couvre-t-elle tous les champs, avec un PDF ?
    candidates = [(lib, ubs) for lib, ubs in enriched_lib
                  if _title_author_year_match(group, lib)]
    if not candidates:
        return {**base, "tier": "loss", "reason": "no_match",
                "missing": [], "matched": None}

    best = None  # (n_missing, has_pdf, lib, missing)
    for lib, ubs in candidates:
        miss = metadata_missing(group, lib)
        has_pdf = bool(ubs)
        score = (len(miss), 0 if has_pdf else 1)
        if best is None or score < best[0]:
            best = (score, lib, miss, has_pdf)
    _, lib, miss, has_pdf = best

    if miss:
        return {**base, "tier": "loss", "reason": "metadata_incomplete",
                "missing": miss, "matched": lib.get("key")}
    # Le PDF n'est requis que si la notice de groupe en porte un (URL présente).
    if gub and not has_pdf:
        return {**base, "tier": "loss", "reason": "no_pdf_on_match",
                "missing": miss, "matched": lib.get("key")}
    return {**base, "tier": "doc_equivalent", "matched": lib.get("key")}


def duplicate_clusters(lib_items: list[dict]) -> list[dict]:
    """Notices My Library partageant (titre normalisé, année) — doublons internes.

    Hors verdict (les doublons sont attendus et acceptés, cf. ticket) : signalé
    pour information seulement.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for d in lib_items:
        key = (norm_text(d.get("title")), norm_year(d.get("date")))
        if not key[0]:
            continue
        groups.setdefault(key, []).append(d.get("key"))
    out = [{"titre": t, "annee": y, "keys": ks}
           for (t, y), ks in groups.items() if len(ks) > 1]
    return sorted(out, key=lambda x: -len(x["keys"]))


def _enrich_library(lib_items: list[dict],
                    children_by_parent: dict[str, list[dict]]) -> list[tuple[dict, set[str]]]:
    """Associe chaque notice My Library aux basenames d'URL d'elle + ses enfants."""
    enriched = []
    for data in lib_items:
        ubs = {url_basename(data.get("url"))}
        for child in children_by_parent.get(data.get("key"), []):
            ubs.add(url_basename(child.get("url")))
            ubs.add(url_basename(child.get("title")))  # filename en pièce jointe
        enriched.append((data, ubs - {""}))
    return enriched


def assess_all(group_items: list[dict], lib_items: list[dict],
               children_by_parent: dict[str, list[dict]],
               group_notes: list[dict] | None = None,
               lib_note_texts: list[str] | None = None) -> dict:
    """Audit complet : partition des notices de groupe et verdict go/no-go.

    `group_items`, `lib_items` : listes de `data` Zotero. `children_by_parent` :
    pièces jointes My Library indexées par clé de notice parente. `group_notes` :
    notes d'annotation du groupe (data). `lib_note_texts` : textes des notes
    My Library. Le verdict tient compte des deux axes : métadonnées/PDF ET notes.
    """
    enriched = _enrich_library(lib_items, children_by_parent)
    url_preserved, doc_equivalent, losses = [], [], []
    for g in group_items:
        r = assess_item(g, enriched)
        if r["tier"] == "url_preserved":
            url_preserved.append(r)
        elif r["tier"] == "doc_equivalent":
            doc_equivalent.append(r)
        else:
            losses.append(r)
    note_losses = unpreserved_notes(group_notes or [], lib_note_texts or [])
    return {
        "total": len(group_items),
        "url_preserved": len(url_preserved),
        "doc_equivalent": len(doc_equivalent),
        "doc_equivalent_list": doc_equivalent,
        "losses": losses,
        "note_losses": note_losses,
        "duplicate_clusters": duplicate_clusters(lib_items),
        "verdict": "go" if not losses and not note_losses else "no-go",
    }


# --- collecte Zotero (réseau, non testé en unitaire) -------------------------

def _children_by_parent(all_items: list[dict]) -> dict[str, list[dict]]:
    """Indexe les notices enfants (pièces jointes) par clé de parent."""
    out: dict[str, list[dict]] = {}
    for it in all_items:
        parent = it["data"].get("parentItem")
        if parent:
            out.setdefault(parent, []).append(it["data"])
    return out


def _fetch_all_items(library: str, api_key: str) -> list[dict]:
    """Toutes les notices d'une bibliothèque (top + enfants), paginées."""
    items, start = [], 0
    while True:
        page, total = rz._get(
            f"{rz.API}/{library}/items?limit=100&start={start}", api_key)
        items.extend(page)
        start += 100
        if start >= total or not page:
            break
    return items


def collect(env_path: Path, group_id: str) -> tuple[list[dict], list[dict],
                                                     dict, list[dict], list[str], dict]:
    """Collecte live, lecture seule.

    Retourne (data notices groupe, data top My Library, pièces jointes My Library
    par parent, notes d'annotation du groupe, textes des notes My Library, méta).
    """
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    user_id = rz.fetch_user_id(api_key)

    all_group = _fetch_all_items(f"groups/{group_id}", api_key)
    all_perso = _fetch_all_items(f"users/{user_id}", api_key)

    def is_doc(d):
        return not d.get("parentItem") and d.get("itemType") not in ("attachment", "note")

    group_data = [it["data"] for it in all_group if is_doc(it["data"])]
    group_notes = [it["data"] for it in all_group if it["data"].get("itemType") == "note"]
    lib_top = [it["data"] for it in all_perso if is_doc(it["data"])]
    lib_note_texts = [it["data"].get("note", "") for it in all_perso
                      if it["data"].get("itemType") == "note"]
    children = _children_by_parent(all_perso)
    meta = {
        "notices_groupe": len(group_data),
        "notes_groupe": len(group_notes),
        "notices_my_library_top": len(lib_top),
        "notices_my_library_total": len(all_perso),
        "notes_my_library": len(lib_note_texts),
        "group_id": group_id,
        "user_id": user_id,
    }
    return group_data, lib_top, children, group_notes, lib_note_texts, meta


def render_markdown(report: dict, meta: dict) -> str:
    """Rapport humain : verdict, liste des pertes (verdict), annexe (hors verdict)."""
    verdict = report["verdict"].upper()
    lines = [
        "# Audit : aucune information perdue avant suppression de `Recueil_CIRED` ?",
        "",
        f"_Ticket 0025 — vérificateur indépendant, lecture seule. Groupe "
        f"{meta['group_id']}, My Library user {meta['user_id']}._",
        "",
        f"## Verdict : **{verdict}**",
        "",
        f"- Notices de groupe auditées : **{report['total']}**",
        f"- URL/PDF du recueil préservée à l'identique : **{report['url_preserved']}**",
        f"- Document équivalent dans My Library (métadonnées + PDF, URL recueil "
        f"non dupliquée) : **{report['doc_equivalent']}**",
        f"- **Pertes métadonnées/PDF : {len(report['losses'])}**",
        f"- **Pertes de notes d'annotation : {len(report['note_losses'])}**",
        "",
    ]
    if not report["losses"] and not report["note_losses"]:
        lines += ["Aucune perte détectée : chaque notice de groupe est couverte "
                  "par My Library (URL identique ou document équivalent) et toutes "
                  "les notes d'annotation y sont retrouvées. Le groupe est "
                  "**supprimable**.", ""]

    if report["losses"]:
        lines += ["## Pertes métadonnées/PDF (verdict)", "",
                  "| key | année | titre | raison | champs manquants |",
                  "|---|---|---|---|---|"]
        for r in report["losses"]:
            title = (r.get("title") or "").replace("|", "\\|")[:70]
            lines.append(
                f"| {r['key']} | {r['annee']} | {title} | {r['reason']} | "
                f"{', '.join(r.get('missing') or []) or '—'} |")
        lines.append("")

    if report["note_losses"]:
        lines += ["## Pertes de notes d'annotation (verdict)", "",
                  "Notes (commentaires d'Antonin) rattachées à des notices de "
                  "groupe, dont le texte est introuvable dans My Library. Leur "
                  "suppression effacerait ces annotations.", "",
                  "| notice parente | extrait |", "|---|---|"]
        for n in report["note_losses"]:
            extrait = (n.get("extrait") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {n.get('parent')} | {extrait} |")
        lines.append("")

    if report["losses"] or report["note_losses"]:
        lines += ["Tant que ces listes ne sont pas vides, **ne pas supprimer le "
                  "groupe**.", ""]

    # Annexe hors verdict : équivalents documentaires (URL recueil non dupliquée).
    lines += ["## Annexe (hors verdict) — URL recueil non dupliquée", "",
              f"{report['doc_equivalent']} notices de groupe ont leurs "
              "métadonnées entièrement couvertes par une notice pré-existante de "
              "My Library qui pointe un PDF du même document (chemin inari "
              "différent). L'URL spécifique du recueil n'y est pas recopiée ; "
              "comme la suppression du groupe Zotero ne supprime aucun fichier "
              "inari, le document reste accessible. Pour information seulement — "
              "n'entre pas dans le go/no-go.", ""]

    dups = report.get("duplicate_clusters", [])
    lines += ["## Annexe (hors verdict) — doublons internes de My Library", ""]
    if dups:
        n_extra = sum(len(d["keys"]) - 1 for d in dups)
        lines += [f"{len(dups)} groupes de notices partagent le même (titre, "
                  f"année), soit {n_extra} notices redondantes. Attendu et accepté "
                  "(cf. ticket) ; signalé pour information. Dix premiers :", "",
                  "| titre | année | nb |", "|---|---|---|"]
        for d in dups[:10]:
            lines.append(f"| {d['titre'][:55]} | {d['annee']} | {len(d['keys'])} |")
        lines.append("")
    else:
        lines += ["Aucun doublon (titre, année) détecté dans My Library.", ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--output-json", type=Path, default=DEFAULT_REPORT_JSON)
    p.add_argument("--output-md", type=Path, default=DEFAULT_REPORT_MD)
    p.add_argument("--cache", type=Path, default=None,
                   help="JSON {group, lib_top, children} pré-collecté (hors réseau)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cache:
        c = json.loads(args.cache.read_text())
        group_data, lib_top, children = c["group"], c["lib_top"], c["children"]
        group_notes, lib_note_texts = c.get("group_notes", []), c.get("lib_note_texts", [])
        meta = c.get("meta", {"group_id": args.group_id, "user_id": "?"})
    else:
        (group_data, lib_top, children,
         group_notes, lib_note_texts, meta) = collect(args.env, args.group_id)

    report = assess_all(group_data, lib_top, children, group_notes, lib_note_texts)
    args.output_json.write_text(
        json.dumps({"meta": meta, **report}, ensure_ascii=False, indent=2))
    args.output_md.write_text(render_markdown(report, meta))

    logger.info("Notices groupe : %d", report["total"])
    logger.info("  URL préservée  : %d", report["url_preserved"])
    logger.info("  doc équivalent : %d", report["doc_equivalent"])
    logger.info("  PERTES méta/PDF: %d", len(report["losses"]))
    logger.info("  PERTES notes   : %d", len(report["note_losses"]))
    logger.info("Verdict : %s", report["verdict"].upper())
    logger.info("Rapport : %s / %s", args.output_json, args.output_md)
    return 0  # audit informatif : un verdict no-go n'est pas un échec d'exécution


if __name__ == "__main__":
    sys.exit(main())
