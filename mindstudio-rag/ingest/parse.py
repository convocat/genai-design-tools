"""HTML → cleaned markdown + outbound link list."""
from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse

from markdownify import markdownify as md
from selectolax.parser import HTMLParser

DROP_SELECTORS = [
    "script", "style", "noscript", "svg", "header", "footer", "nav",
    "[role=navigation]", "[role=banner]", "[role=contentinfo]",
    ".navigation", ".navbar", ".sidebar", ".cookie", ".cookies",
    ".breadcrumb", ".breadcrumbs",
]


def parse_page(url: str, html: str, base_host: str) -> dict:
    tree = HTMLParser(html)

    title = ""
    if tree.css_first("title"):
        title = (tree.css_first("title").text() or "").strip()
    h1 = tree.css_first("h1")
    if h1:
        title = (h1.text() or title).strip()

    main = tree.css_first("main") or tree.css_first("article") or tree.body
    if main is None:
        return {"url": url, "title": title, "markdown": "", "links": []}

    for sel in DROP_SELECTORS:
        for n in main.css(sel):
            n.decompose()

    links: list[str] = []
    for a in main.css("a[href]"):
        href = a.attributes.get("href") or ""
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        nxt, _ = urldefrag(urljoin(url, href))
        if urlparse(nxt).hostname == base_host:
            links.append(nxt.rstrip("/"))

    raw_html = main.html or ""
    markdown = md(raw_html, heading_style="ATX", strip=["a", "img"]).strip()

    # Collapse 3+ blank lines
    cleaned: list[str] = []
    blank = 0
    for line in markdown.splitlines():
        if not line.strip():
            blank += 1
            if blank <= 1:
                cleaned.append("")
        else:
            blank = 0
            cleaned.append(line.rstrip())
    markdown = "\n".join(cleaned).strip()

    return {
        "url": url,
        "title": title or url,
        "markdown": markdown,
        "links": sorted(set(links)),
    }
