"""Product documentation: Markdown articles in app/content/help, served to the in-app Documentation section.

Each article starts with a small front-matter block:

    ---
    title: Controls
    section: Compliance
    order: 20
    summary: One sentence shown in the index and search results.
    routes: /controls, /controls/*        (app pages this article explains; drives the "Help" link)
    ---

Articles are read once and cached. They contain no customer data, so the endpoints are public.
"""
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

HELP_DIR = Path(__file__).resolve().parent.parent / "content" / "help"
SECTIONS = ["Get started", "Compliance", "Evidence and audits", "People and training", "DPDP and privacy",
            "Risk and vendors", "Automation", "Administration", "Reference"]
SLUG_RE = re.compile(r"^[a-z0-9-]{1,80}$")


class HelpError(ValueError):
    pass


@dataclass
class Article:
    slug: str
    title: str
    section: str
    order: int
    summary: str
    routes: list[str]
    body_md: str
    headings: list[dict] = field(default_factory=list)
    text: str = ""

    def card(self) -> dict:
        return {"slug": self.slug, "title": self.title, "section": self.section, "order": self.order,
                "summary": self.summary, "routes": self.routes}


def anchor(text: str) -> str:
    """Same rule as the frontend uses for heading ids."""
    s = re.sub(r"[`*_]", "", text.lower())
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s-]+", "-", s).strip("-")[:80]


def _parse(path: Path) -> Article:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise HelpError(f"{path.name}: missing front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).strip() + "\n"
    slug = path.stem
    if not SLUG_RE.match(slug):
        raise HelpError(f"{path.name}: invalid file name")
    for key in ("title", "section", "summary"):
        if not meta.get(key):
            raise HelpError(f"{path.name}: front matter needs {key}")
    if meta["section"] not in SECTIONS:
        raise HelpError(f"{path.name}: unknown section {meta['section']!r}")
    headings = []
    in_code = False
    for line in body.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_code = not in_code
            continue
        h = re.match(r"^(##|###) (.+)$", line)
        if h and not in_code:
            headings.append({"level": len(h.group(1)), "text": h.group(2).strip(), "id": anchor(h.group(2))})
    plain = re.sub(r"```.*?```", " ", body, flags=re.S)
    plain = re.sub(r"[#>*_`|]|\[([^\]]*)\]\([^)]*\)", lambda x: x.group(1) or " ", plain)
    routes = [r.strip() for r in str(meta.get("routes", "")).split(",") if r.strip()]
    return Article(slug, meta["title"], meta["section"], int(meta.get("order", 100)), meta["summary"], routes, body,
                   headings, re.sub(r"\s+", " ", plain))


@lru_cache(maxsize=1)
def articles() -> dict[str, Article]:
    found = [_parse(p) for p in sorted(HELP_DIR.glob("*.md"))]
    ordered = sorted(found, key=lambda a: (SECTIONS.index(a.section), a.order, a.title))
    return {a.slug: a for a in ordered}


def validate() -> int:
    """Check every article parses and every internal link points at an existing article and heading."""
    arts = articles()
    for a in arts.values():
        for target in re.findall(r"\]\(/docs/([a-z0-9-]+)(?:#([a-z0-9-]+))?\)", a.body_md):
            slug, frag = target
            if slug not in arts:
                raise HelpError(f"{a.slug}: link to unknown article /docs/{slug}")
            if frag and frag not in {h["id"] for h in arts[slug].headings}:
                raise HelpError(f"{a.slug}: link to unknown heading /docs/{slug}#{frag}")
    return len(arts)


def index() -> dict:
    arts = list(articles().values())
    return {"sections": [{"title": s, "articles": [a.card() for a in arts if a.section == s]}
                         for s in SECTIONS if any(a.section == s for a in arts)]}


def get(slug: str) -> dict | None:
    arts = articles()
    a = arts.get(slug)
    if not a:
        return None
    keys = list(arts)
    i = keys.index(slug)
    prev_a = arts[keys[i - 1]] if i > 0 else None
    next_a = arts[keys[i + 1]] if i + 1 < len(keys) else None
    return {**a.card(), "body_md": a.body_md, "headings": a.headings,
            "prev": prev_a.card() if prev_a else None, "next": next_a.card() if next_a else None}


def for_route(path: str) -> dict | None:
    """The article that explains an app page, for the contextual Help link. Most specific match wins."""
    best, best_len = None, -1
    for a in articles().values():
        for r in a.routes:
            if r.endswith("/*"):
                base = r[:-2]
                ok = path == base or path.startswith(base + "/")
            else:
                ok = path == r
            if ok and len(r) > best_len:
                best, best_len = a, len(r)
    return best.card() if best else None


def search(q: str, limit: int = 20) -> list[dict]:
    words = [w for w in re.findall(r"[a-z0-9-]{2,}", q.lower())][:8]
    if not words:
        return []
    results = []
    for a in articles().values():
        title, low = a.title.lower(), a.text.lower()
        if not all(w in low or w in title for w in words):
            continue
        score = sum(10 * (w in title) + 4 * any(w in h["text"].lower() for h in a.headings) + min(low.count(w), 10)
                    for w in words)
        pos = min((low.find(w) for w in words if w in low), default=0)
        start = max(0, pos - 80)
        snippet = ("…" if start else "") + a.text[start:start + 220].strip() + "…"
        heading = next((h for h in a.headings if any(w in h["text"].lower() for w in words)), None)
        results.append({**a.card(), "snippet": snippet, "heading": heading, "score": score})
    return sorted(results, key=lambda r: -r["score"])[:limit]
