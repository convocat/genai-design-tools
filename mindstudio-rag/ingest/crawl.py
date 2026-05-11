"""Same-host BFS crawler for MindStudio University docs.

Strategy:
1. Try /sitemap.xml first (fast and exhaustive when available).
2. Fall back to BFS from the base URL, following only same-host links
   to text/html pages.

Returns a list of (url, html) tuples.
"""
from __future__ import annotations

import re
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

USER_AGENT = "MindStudio-RAG-Bot/0.1 (one-shot ingest; contact: maaike.ai)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}


def _normalize(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/")


def _same_host(url: str, base_host: str) -> bool:
    try:
        return urlparse(url).hostname == base_host
    except Exception:
        return False


_NON_HTML_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|pdf|zip|tar|gz|mp4|mp3|wav|css|js|json|xml|ico)$", re.I)


def _looks_like_html(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not bool(_NON_HTML_EXT.search(path))


def fetch_sitemap_urls(client: httpx.Client, base_url: str) -> list[str]:
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    try:
        r = client.get(sitemap_url, timeout=15)
        if r.status_code != 200 or "<urlset" not in r.text and "<sitemapindex" not in r.text:
            return []
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
        return [_normalize(u) for u in urls]
    except Exception:
        return []


def crawl(base_url: str, max_pages: int = 500, delay_s: float = 0.3,
          progress=print) -> list[tuple[str, str]]:
    base_host = urlparse(base_url).hostname or ""
    visited: set[str] = set()
    out: list[tuple[str, str]] = []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        seeds = fetch_sitemap_urls(client, base_url)
        if seeds:
            progress(f"[crawl] sitemap returned {len(seeds)} URLs")
            for s in seeds[:5]:
                progress(f"[crawl]   sample: {s}")
        else:
            progress("[crawl] no sitemap, BFS from base URL")
        # Always include base URL so we can BFS even if sitemap misses pages.
        seeds = list(seeds) + [_normalize(base_url)]
        same_host_seeds = [u for u in seeds if _same_host(u, base_host)]
        if not same_host_seeds:
            progress(f"[crawl] WARN: no seeds match base_host={base_host}; falling back to base URL alone")
            same_host_seeds = [_normalize(base_url)]
        queue = deque(same_host_seeds)
        while queue and len(out) < max_pages:
            url = queue.popleft()
            url = _normalize(url)
            if url in visited:
                continue
            visited.add(url)
            try:
                r = client.get(url)
            except Exception as e:
                progress(f"[crawl] skip {url}: {e}")
                continue
            if r.status_code != 200:
                continue
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype.lower():
                continue
            html = r.text
            out.append((url, html))
            progress(f"[crawl] {len(out):>3}. {url}")
            time.sleep(delay_s)

            tree = HTMLParser(html)
            for a in tree.css("a[href]"):
                href = a.attributes.get("href") or ""
                if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
                    continue
                nxt = _normalize(urljoin(url, href))
                if not _same_host(nxt, base_host) or not _looks_like_html(nxt):
                    continue
                if nxt not in visited:
                    queue.append(nxt)

    return out
