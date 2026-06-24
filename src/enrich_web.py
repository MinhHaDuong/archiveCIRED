"""Enrichir les notices via recherche web (ticket 0024) — filet de rattrapage.

Pour les notices absentes de HAL et OpenAlex, cherche via DuckDuckGo Lite,
extrait les métadonnées de la page faisant autorité (Highwire, Dublin Core,
JSON-LD, OpenGraph), propose l'url et les champs manquants.

Lecture seule : rapport JSON + Markdown. Écriture via apply_corrections.py.
Vérification humaine OBLIGATOIRE : résultats web non fiables.
"""

import argparse
import json
import logging
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz

_STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to",
         "de", "la", "le", "les", "des", "du", "un", "une", "et", "pour",
         "dans", "sur"}


def norm_tokens(s: str | None) -> set[str]:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return {t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
            if len(t) > 1 and t not in _STOP}


def jaccard(a: str, b: str) -> float:
    A, B = norm_tokens(a), norm_tokens(b)
    return len(A & B) / len(A | B) if (A | B) else 0.0


def lastnames(creators: list[dict] | None) -> set[str]:
    out: set[str] = set()
    for c in creators or []:
        n = c.get("lastName") or c.get("name") or ""
        out |= norm_tokens(n)
    return out


def year_of(date: str | None) -> str:
    m = re.search(r"\d{4}", date or "")
    return m.group(0) if m else ""

logger = logging.getLogger("enrich_web")

DEFAULT_OUTPUT = Path("outputs/enrich_web_report.json")
DDG_LITE = "https://lite.duckduckgo.com/lite/"
HEADERS = {"User-Agent": "archiveCIRED/1.0 (contact: minh.haduong@gmail.com)"}

# notice Zotero ← clé candidate web
_FIELD_MAP = {
    "publicationTitle": "journalTitle",
    "volume": "volume",
    "issue": "issue",
    "pages": "pages",
    "DOI": "doi",
    "date": "year",
}


# ---------------------------------------------------------------------------
# Parseurs HTML (purs)
# ---------------------------------------------------------------------------

class DDGResultParser(HTMLParser):
    """Extrait les URLs de résultats depuis le HTML de DuckDuckGo Lite."""

    def __init__(self):
        super().__init__()
        self._urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if href.startswith("http") and "duckduckgo.com" not in href:
            self._urls.append(href)

    @property
    def urls(self) -> list[str]:
        return self._urls


class MetaExtractor(HTMLParser):
    """Extrait les métadonnées académiques d'une page HTML.

    Supporte par ordre de priorité :
    1. Highwire Press  (citation_title, citation_author, …)
    2. Dublin Core     (DC.title, DC.creator, …)
    3. JSON-LD         (ScholarlyArticle, Article, Book, …)
    4. OpenGraph       (og:title — fallback titre seul)
    """

    def __init__(self):
        super().__init__()
        self._m: dict = {}
        self._in_ld = False
        self._ld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        a = dict(attrs)
        if tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            content = a.get("content") or ""
            self._absorb(name, prop, content)
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld = True
            self._ld_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self._parse_ld("".join(self._ld_buf))

    def _absorb(self, name: str, prop: str, content: str) -> None:
        m = self._m
        # Highwire Press
        if name == "citation_title":
            m.setdefault("title", content)
        elif name == "citation_author":
            m.setdefault("authors", []).append(content)
        elif name in ("citation_year", "citation_publication_date"):
            m.setdefault("year", content[:4])
        elif name == "citation_doi":
            m.setdefault("doi", content)
        elif name == "citation_journal_title":
            m.setdefault("journalTitle", content)
        elif name == "citation_volume":
            m.setdefault("volume", content)
        elif name == "citation_firstpage":
            m.setdefault("pages", content)
        # Dublin Core
        elif name == "dc.title":
            m.setdefault("title", content)
        elif name == "dc.creator":
            m.setdefault("authors", []).append(content)
        elif name == "dc.date":
            m.setdefault("year", content[:4])
        elif name in ("dc.identifier", "dc.relation"):
            doi = _doi_from_str(content)
            if doi:
                m.setdefault("doi", doi)
        # OpenGraph (fallback titre uniquement)
        elif prop == "og:title":
            m.setdefault("_og_title", content)

    def _parse_ld(self, text: str) -> None:
        try:
            data = json.loads(text)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        accepted = {"ScholarlyArticle", "Article", "Book", "Chapter", "CreativeWork"}
        if data.get("@type", "") not in accepted:
            return
        m = self._m
        if data.get("name"):
            m.setdefault("title", data["name"])
        if data.get("datePublished"):
            m.setdefault("year", str(data["datePublished"])[:4])
        doi = _doi_from_str(str(data.get("identifier") or ""))
        if doi:
            m.setdefault("doi", doi)
        authors = data.get("author") or []
        if isinstance(authors, list):
            for a in authors:
                nm = (a.get("name") if isinstance(a, dict) else str(a)) or ""
                if nm:
                    m.setdefault("authors", []).append(nm)

    @property
    def result(self) -> dict:
        out = {k: v for k, v in self._m.items() if k != "_og_title"}
        if not out.get("title") and self._m.get("_og_title"):
            out["title"] = self._m["_og_title"]
        return out


def _doi_from_str(s: str) -> str:
    """Extrait un DOI d'une chaîne (doi:, https://doi.org/, ou 10.xxx/…)."""
    if not s:
        return ""
    s = re.sub(r".*doi\.org/", "", s).strip()
    s = re.sub(r"^doi:", "", s).strip()
    return s if re.match(r"^10\.\d{4,}/", s) else ""


# ---------------------------------------------------------------------------
# Fonctions pures exportées
# ---------------------------------------------------------------------------

def extract_meta(html: str) -> dict:
    """Extrait les métadonnées académiques d'une chaîne HTML."""
    p = MetaExtractor()
    p.feed(html)
    return p.result


def proposed_web_diff(notice: dict, candidate: dict) -> dict:
    """URL + champs que le candidat apporte et que la notice n'a pas.

    Retourne {url, add:{champ:val}, differ:{champ:(notice,candidat)}}.
    """
    add: dict = {}
    differ: dict = {}
    for zf, cf in _FIELD_MAP.items():
        cv = str(candidate.get(cf) or "").strip()
        if not cv:
            continue
        nv = str(notice.get(zf) or "").strip()
        if not nv:
            add[zf] = cv
        elif norm_tokens(nv) != norm_tokens(cv):
            differ[zf] = (nv, cv)
    return {"url": candidate.get("url", ""), "add": add, "differ": differ}


def match_web(notice: dict, candidates: list[dict],
              threshold: float = 0.5) -> dict | None:
    """Meilleur candidat web corroboré, ou None.

    Corroboration : Jaccard(titre) ≥ threshold ET ≥1 auteur commun ET
    (année ±1 ou absente d'un côté).
    """
    n_authors = lastnames(notice.get("creators"))
    n_year = year_of(notice.get("date"))
    best = None
    for c in candidates:
        sim = jaccard(notice.get("title", ""), c.get("title", ""))
        if sim < threshold:
            continue
        c_authors = {t for a in c.get("authors", []) for t in norm_tokens(a)}
        if n_authors and c_authors and not (n_authors & c_authors):
            continue
        cy = str(c.get("year") or "")
        if n_year and cy and abs(int(n_year) - int(cy)) > 1:
            continue
        score = (round(sim, 3),)
        if best is None or score > best[0]:
            best = (score, c, sim)
    if not best:
        return None
    return {**best[1], "title_sim": round(best[2], 3)}


# ---------------------------------------------------------------------------
# Réseau
# ---------------------------------------------------------------------------

def ddg_search(query: str, max_results: int = 5,
               pause: float = 1.0) -> list[str]:
    """Retourne les URLs des premiers résultats DuckDuckGo Lite."""
    params = {"q": query, "kl": "fr-fr"}
    url = DDG_LITE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("DDG search échoué : %s", e)
        return []
    time.sleep(pause)
    p = DDGResultParser()
    p.feed(html)
    return p.urls[:max_results]


def fetch_page(url: str, timeout: int = 15) -> str | None:
    """Récupère le HTML d'une URL (None si non-HTML ou erreur)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get_content_type() or ""
            if "html" not in ct:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("fetch %s : %s", url, e)
        return None


def build_candidates(notice: dict, max_urls: int,
                     pause: float) -> list[dict]:
    """Cherche via DDG, extrait les métadonnées de chaque page résultat."""
    title = notice.get("title", "")
    authors = sorted(lastnames(notice.get("creators")))
    first = authors[0] if authors else ""
    query = f"{title} {first}".strip()
    urls = ddg_search(query, max_results=max_urls, pause=pause)
    candidates: list[dict] = []
    for url in urls:
        html = fetch_page(url)
        if not html:
            continue
        meta = extract_meta(html)
        if meta.get("title"):
            meta["url"] = url
            candidates.append(meta)
        time.sleep(pause * 0.3)
    return candidates


def enrich_one(notice: dict, pause: float, threshold: float,
               max_urls: int) -> dict:
    """Cherche, apparie et propose le diff pour une notice (réseau)."""
    res: dict = {"key": notice.get("key"), "title": notice.get("title", ""),
                 "matched": None}
    try:
        candidates = build_candidates(notice, max_urls, pause)
    except Exception as e:
        logger.warning("  web KO pour %s : %s", notice.get("key"), e)
        return {**res, "error": str(e)[:80]}
    best = match_web(notice, candidates, threshold)
    if best:
        res["matched"] = {"url": best.get("url", ""),
                          "title_sim": best.get("title_sim", 0.0)}
        res["diff"] = proposed_web_diff(notice, best)
    return res


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def summarize(results: list[dict]) -> dict:
    matched = [r for r in results if r.get("matched")]
    with_url = [r for r in matched if r.get("diff", {}).get("url")]
    return {"total": len(results), "matched": len(matched),
            "with_url": len(with_url),
            "unmatched": len(results) - len(matched)}


def render_markdown(results: list[dict], summary: dict) -> str:
    pct = 100 * summary["matched"] // max(1, summary["total"])
    lines = [
        "# Enrichissement web — rapport (ticket 0024, revue avant écriture)\n",
        f"- notices traitées : **{summary['total']}**",
        f"- appariées : **{summary['matched']}** ({pct} %)",
        f"- avec url trouvée : **{summary['with_url']}**",
        f"- non appariées : **{summary['unmatched']}**\n",
        "## Appariées avec propositions\n",
        "| key | sim | url | champs à ajouter | divergences |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        if not r.get("matched"):
            continue
        d = r.get("diff", {})
        add = ", ".join(f"{k}={str(v)[:20]}" for k, v in d.get("add", {}).items())
        dif = ", ".join(d.get("differ", {}).keys())
        url = (r["matched"].get("url") or "")[:60]
        lines.append(f"| {r['key']} | {r['matched']['title_sim']} | "
                     f"{url} | {add} | {dif} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=rz.DEFAULT_ENV)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--limit", type=int, default=20,
                   help="taille du lot (0 = tout)")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--types",
                   default="journalArticle,bookSection,conferencePaper,report",
                   help="itemTypes à traiter (séparés par des virgules)")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--pause", type=float, default=1.5,
                   help="pause inter-requête (s)")
    p.add_argument("--max-urls", type=int, default=5,
                   help="URLs DDG à explorer par notice")
    p.add_argument("--no-url", action="store_true",
                   help="traiter aussi les notices qui ont déjà une url")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)
    types = set(args.types.split(","))
    all_items = [it["data"] for it in rz.fetch_top_items(f"users/{uid}", api_key)
                 if it["data"].get("itemType") in types]
    if not args.no_url:
        all_items = [it for it in all_items if not it.get("url")]
    batch = (all_items[args.offset:] if args.limit == 0
             else all_items[args.offset:args.offset + args.limit])
    logger.info("Notices éligibles : %d | lot traité : %d",
                len(all_items), len(batch))

    results = []
    for i, n in enumerate(batch, 1):
        results.append(enrich_one(n, args.pause, args.threshold, args.max_urls))
        if i % 5 == 0:
            logger.info("  %d/%d…", i, len(batch))

    summary = summarize(results)
    args.output.write_text(
        json.dumps({"summary": summary, "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    args.output.with_suffix(".md").write_text(
        render_markdown(results, summary), encoding="utf-8")
    logger.info("Appariées %d/%d · avec url %d · rapport %s",
                summary["matched"], summary["total"],
                summary["with_url"], args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
