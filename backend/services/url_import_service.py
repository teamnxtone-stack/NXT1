"""URL Revamp / Import Service.

Implements the "paste-a-website" import path:
  1. Fetch the live page over HTTPS
  2. Extract structure (HTML), text content, navigation, headings, CTAs
  3. Pull design tokens (primary color, font family, key images)
  4. Hand a structured `BluePrint` to the builder so generation can re-create
     the same site using NXT1's premium component registry instead of
     literal-HTML copying.

Notes:
  - We deliberately do not embed the original HTML. The goal is REVAMP, not
    clone — so we strip down to a token / blueprint that the builder reuses.
  - We use `httpx` + `BeautifulSoup` (already installed). Headless screenshots
    are out-of-scope for the first cut; if a Playwright sidecar is wired
    later it plugs into `_capture_screenshot`.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("nxt1.url_import")

UA = "NXT1-Importer/1.0 (+https://nxtone.tech)"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)


async def fetch_html(url: str) -> tuple[str, str]:
    """Fetch the page and return (final_url, html)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept": "text/html"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return str(r.url), r.text


def _safe_text(node) -> str:
    if not node:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True))[:1000]


def _extract_color_palette(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Pull obvious primary colors from inline styles + theme-color meta."""
    palette: list[str] = []
    meta = soup.find("meta", attrs={"name": "theme-color"})
    if meta and meta.get("content"):
        palette.append(meta["content"].strip())
    # Common CSS variables in <style> blocks
    style_text = " ".join(s.get_text() for s in soup.find_all("style"))
    for m in re.finditer(r"#([0-9a-fA-F]{6})\b", style_text):
        c = f"#{m.group(1)}"
        if c not in palette:
            palette.append(c)
        if len(palette) >= 8:
            break
    return palette


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    nav = soup.find("nav") or soup.find("header")
    links: list[dict] = []
    seen: set[str] = set()
    if nav:
        for a in nav.find_all("a", href=True)[:12]:
            href = urljoin(base_url, a["href"])
            label = a.get_text(strip=True)[:60]
            if not label or label.lower() in seen:
                continue
            seen.add(label.lower())
            links.append({"label": label, "href": href})
    return links


def _extract_sections(soup: BeautifulSoup) -> list[dict]:
    sections: list[dict] = []
    for sect in (soup.find_all(["section", "article", "div"], limit=80)):
        h = sect.find(["h1", "h2", "h3"])
        if not h:
            continue
        heading = h.get_text(strip=True)
        if not heading or len(heading) < 3:
            continue
        body = _safe_text(sect)
        if len(body) < 60:
            continue
        sections.append({
            "heading": heading[:120],
            "level": h.name,
            "body": body[:600],
            "kind": _classify_section(heading, body),
        })
        if len(sections) >= 8:
            break
    return sections


def _classify_section(heading: str, body: str) -> str:
    h = heading.lower()
    if any(k in h for k in ("price", "plan", "tier")):
        return "pricing"
    if any(k in h for k in ("feature", "what we", "what you", "why ")):
        return "features"
    if any(k in h for k in ("testimon", "review", "loved by", "trusted")):
        return "testimonials"
    if any(k in h for k in ("faq", "question")):
        return "faq"
    if any(k in h for k in ("contact", "get in touch", "demo")):
        return "contact"
    if any(k in h for k in ("about", "story", "mission")):
        return "about"
    return "section"


def _extract_hero(soup: BeautifulSoup) -> dict:
    h1 = soup.find("h1")
    return {
        "title": h1.get_text(strip=True)[:160] if h1 else "",
        "subtitle": _safe_text(h1.find_next("p") if h1 else None)[:240],
    }


def _extract_brand(soup: BeautifulSoup) -> dict:
    title = soup.find("title")
    site_name = soup.find("meta", attrs={"property": "og:site_name"})
    description = soup.find("meta", attrs={"name": "description"})
    return {
        "name": (site_name["content"] if site_name and site_name.get("content")
                 else (title.get_text(strip=True) if title else ""))[:120],
        "tagline": (description["content"][:240] if description and description.get("content")
                    else ""),
    }


def _extract_fonts(soup: BeautifulSoup) -> list[str]:
    """Heuristic: pick up @font-face URLs + Google Fonts <link>."""
    fonts: list[str] = []
    for link in soup.find_all("link", href=True):
        href = link["href"]
        if "fonts.googleapis.com" in href:
            m = re.search(r"family=([^&:]+)", href)
            if m:
                fonts.append(m.group(1).replace("+", " "))
    return list(dict.fromkeys(fonts))[:4]


async def analyze_url(url: str) -> dict:
    """Top-level — fetch + parse + return a BluePrint."""
    final_url, html = await fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    blueprint = {
        "source_url": final_url,
        "brand": _extract_brand(soup),
        "hero": _extract_hero(soup),
        "navigation": _extract_links(soup, final_url),
        "sections": _extract_sections(soup),
        "palette": _extract_color_palette(soup, final_url),
        "fonts": _extract_fonts(soup),
        "host": urlparse(final_url).netloc,
        "title": (soup.find("title").get_text(strip=True) if soup.find("title") else "")[:160],
    }
    return blueprint
