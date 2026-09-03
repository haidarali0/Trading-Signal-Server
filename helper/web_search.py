import os
import re
from typing import List, Dict, Any

import requests


DEFAULT_SEARCH_TERMS = [
    "crypto",
    "news",
    "regulation",
    "policy",
    "market",
]


# Function: build_search_query
def build_search_query(symbol: str) -> str:
    base_symbol = symbol.replace("USDT", "").replace("USD", "")
    base_symbol = re.sub(r"[^A-Za-z0-9]+", " ", base_symbol).strip().upper()
    terms = [base_symbol or symbol]
    terms.extend(DEFAULT_SEARCH_TERMS)
    return " ".join(terms)


# Function: format_web_search_results
def format_web_search_results(symbol: str, results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""

    lines = [f"Web context for {symbol}:"]
    for idx, item in enumerate(results[:5], start=1):
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        snippet = item.get("snippet") or ""
        lines.append(f"{idx}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   Summary: {snippet}")
    return "\n".join(lines)


# Function: search_web_context
def search_web_context(symbol: str, max_results: int = 5) -> str:
    query = build_search_query(symbol)
    search_url = "https://duckduckgo.com/html/"
    params = {"q": query, "kl": "us-en"}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as exc:
        return f"Web search unavailable: {exc}"

    matches = []
    for result in response.text.split("<a rel=\"nofollow\" class=\"result__a\""):
        if "href=" not in result:
            continue
        title_match = re.search(r">(.*?)<", result, re.S)
        url_match = re.search(r'href="(.*?)"', result)
        snippet_match = re.search(r'<a class="result__snippet"(.*?)>(.*?)</a>', result, re.S)
        if title_match and url_match:
            title = re.sub(r"<.*?\>", "", title_match.group(1)).strip()
            snippet = re.sub(r"<.*?\>", "", snippet_match.group(2)).strip() if snippet_match else ""
            matches.append({"title": title, "url": url_match.group(1), "snippet": snippet})
        if len(matches) >= max_results:
            break

    return format_web_search_results(symbol, matches)
