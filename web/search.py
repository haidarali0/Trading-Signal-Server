# search_web_context.py

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta
import dateutil.parser
import requests

from .trading_keywords import *

def _naive_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo:
        return value.astimezone().replace(tzinfo=None)
    return value


def extract_datetime_from_text(text: str) -> Optional[datetime]:
    try:
        return dateutil.parser.parse(text, fuzzy=True)
    except Exception:
        return None


def extract_datetime_from_url(url: str) -> Optional[datetime]:
    try:
        m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
        if m:
            y, mth, d = m.groups()
            return datetime(int(y), int(mth), int(d))
    except Exception:
        pass
    return None


def compute_recency_score(published_at: Optional[datetime], reference_time: Optional[datetime] = None) -> float:
    published_at = _naive_datetime(published_at)
    if not published_at:
        return 0.0
    now = _naive_datetime(reference_time) or datetime.utcnow()
    diff = now - published_at
    if diff < timedelta(0):
        return -10.0
    if diff < timedelta(hours=1):
        return 4.0
    if diff < timedelta(hours=6):
        return 3.0
    if diff < timedelta(hours=24):
        return 2.0
    if diff < timedelta(days=3):
        return 1.0
    return 0.5


def build_search_query(symbol: str, aspects: Optional[List[str]] = None, extra_terms: Optional[List[str]] = None) -> str:
    base_symbol = symbol.replace("USDT", "").replace("USD", "")
    base_symbol = re.sub(r"[^A-Za-z0-9]+", " ", base_symbol).strip().upper()

    terms = [base_symbol or symbol]
    terms.append("crypto")
    terms.extend(aspects or ["crypto", "news", "regulation", "policy", "market"])

    if extra_terms:
        terms.extend(extra_terms)

    if any(t.lower() in {"news","policy","regulation","macro","exchange","update","updates"} for t in terms):
        terms.extend(["latest","breaking","today"])
    else:
        terms.extend(["latest","news"])

    return " ".join(dict.fromkeys(terms))


def format_web_search_results(symbol: str, results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""

    top_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)[:5]
    final_accuracy = sum(r.get("score", 0) for r in top_results) / len(top_results)

    lines = [f"Web context for {symbol} (Top 5, accuracy={final_accuracy:.2f}):"]

    for i, item in enumerate(top_results, start=1):
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        snippet = item.get("snippet") or ""
        score = item.get("score", 0)
        published_at = item.get("published_at") or "Unknown"

        lines.append(f"{i}. {title}")
        lines.append(f"   URL: {url}")
        lines.append(f"   Summary: {snippet[:500]}...")
        lines.append(f"   Score: {score}")
        lines.append(f"   Time: {published_at}")

    return "\n".join(lines)


def _clean_ddg_url(raw_url: str) -> str:
    """Extract real destination URL from DuckDuckGo redirect link."""
    if "duckduckgo.com/l/?" in raw_url or "uddg=" in raw_url:
        parsed = urlparse(raw_url)
        query_params = parse_qs(parsed.query)
        if "uddg" in query_params:
            return unquote(query_params["uddg"][0])
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    return raw_url


def _get_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc
    except Exception:
        return ""

def clean_html(html: str) -> str:
    # Remove standard non-content tags
    text = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S)
    text = re.sub(r"<style.*?>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<head.*?>.*?</head>", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

    # Remove non-content UI containers
    text = re.sub(r"<(nav|header|footer|aside|form).*?>.*?</\1>", "", text, flags=re.S)

    # Strip remaining HTML tags
    text = re.sub(r"<.*?>", " ", text)

    # Strip inline JS code snippets (DOM manipulation, event handlers, JS statements)
    text = re.sub(r"\b(const|let|var|function|document|window)\b.*?;", "", text)
    text = re.sub(r"[\w\.]+\([\s\S]*?\)", "", text)  # Strips method calls like getElementById()

    # Normalize whitespace
    return re.sub(r"\s+", " ", text).strip()

from typing import List

from typing import List
import re

JS_NOISE_TERMS = {
    "document.", "getelementbyid", "queryselector", "innerhtml", 
    "toectstring", "touppercase", "function(", "const ", "let ", "var "
}

def extract_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    valid_sentences = []

    for p in parts:
        clean_p = p.strip()
        length = len(clean_p)
        low_p = clean_p.lower()

        # 1. Skip short fragments, text dumps, and boilerplate
        if length < 40 or length > 350:
            continue
        if any(term in low_p for term in BOILERPLATE_TERMS):
            continue

        # 2. Reject inline JavaScript fragments
        if any(js in low_p for js in JS_NOISE_TERMS) or "=>" in clean_p or "{" in clean_p:
            continue

        # 3. Ensure full sentence structure
        if not clean_p.endswith((".", "!", "?")):
            continue

        # 4. Check for metrics or trading terms
        has_metrics = bool(METRIC_REGEX.search(clean_p))
        has_market_term = any(term in low_p for term in MARKET_TERMS)

        if has_metrics or has_market_term:
            valid_sentences.append(clean_p)

    return valid_sentences


def score_sentence(s, symbol):
    ls = s.lower()
    score = 0
    score += 15 * sum(ls.count(x) for x in HIGH_IMPACT)
    score += 7  * sum(ls.count(x) for x in MEDIUM_IMPACT)
    score += 2  * sum(ls.count(x) for x in LOW_IMPACT)
    score += 10 * sum(ls.count(x) for x in SYMBOL_KEYWORDS.get(symbol.upper(), []))
    score += 10 * sum(ls.count(x) for x in NEGATIVE_SENTIMENT)
    score += 5  * sum(ls.count(x) for x in POSITIVE_SENTIMENT)
    return score


def extract_useful_info(html: str, symbol: str) -> str:
    text = clean_html(html)
    sentences = extract_sentences(text)
    
    if not sentences:
        return ""

    # Score sentences using existing score_sentence logic
    scored = [(score_sentence(s, symbol), s) for s in sentences]
    scored.sort(reverse=True, key=lambda x: x[0])

    # Pick top 5 scored sentences
    top_sentences = [s for _, s in scored[:5]]

    # Join into a single clean paragraph
    return " ".join(top_sentences).strip()


def score_trading_importance(text: str, symbol: str) -> int:
    t = text.lower()
    score = 0
    score += 15 * sum(t.count(x) for x in HIGH_IMPACT)
    score += 7  * sum(t.count(x) for x in MEDIUM_IMPACT)
    score += 2  * sum(t.count(x) for x in LOW_IMPACT)
    score += 10 * sum(t.count(x) for x in SYMBOL_KEYWORDS.get(symbol.upper(), []))
    score -= 10 * sum(t.count(x) for x in NEGATIVE_SENTIMENT)
    score += 5  * sum(t.count(x) for x in POSITIVE_SENTIMENT)
    return score


def _score_result(result: Dict[str, Any], symbol: str, aspect_terms: List[str], additional_priority_domains: Optional[List[str]] = None) -> int:
    title = (result.get("title") or "")
    snippet = (result.get("snippet") or "")
    url = (result.get("url") or "")
    text = f"{title} {snippet} {url}".lower()
    domain = _get_domain(url)

    score = 0

    if symbol.lower().replace("usdt","") in text:
        score += 4
    if any(t.lower() in text for t in aspect_terms if t):
        score += 2
    if any(t.lower() in text for t in NEWS_TERMS):
        score += 2

    priority_domains = set(PRIORITY_DOMAINS)
    if additional_priority_domains:
        priority_domains.update(d.lower() for d in additional_priority_domains if d)

    # --- UPDATED DOMAIN PRIORITY SCORING ---
    # Assign massive score boosts to domains where full content is extracted
    if domain in WHALE_DOMAINS:
        score += 100
    elif domain in priority_domains:
        score += 80

    if domain in IGNORED_DOMAINS:
        score -= 50

    if not snippet:
        score -= 2

    return score


def scrape_full_page(url: str) -> str:
    if not url:
        return ""
    
    # Ensure scheme exists before passing to Jina
    if url.startswith("//"):
        url = f"https:{url}"
    elif not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    # 1. Primary Attempt: Jina AI Reader
    try:
        cf_url = f"https://r.jina.ai/{url}"
        r = requests.get(cf_url, timeout=20, headers=headers)
        if r.status_code == 200 and r.text.strip():
            return r.text
    except Exception:
        pass

    # 2. Direct Fallback: Direct Scraping if Jina fails or rate-limits
    try:
        r = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    return ""


def search_web_context(symbol: str, aspects: Optional[List[str]] = None, extra_terms: Optional[List[str]] = None, max_results: int = 5, as_of: Optional[datetime] = None, require_published_at: bool = False, additional_priority_domains: Optional[List[str]] = None, enrich_results: bool = True) -> Dict[str, Any]:
    as_of = _naive_datetime(as_of)
    query = build_search_query(symbol, aspects=aspects, extra_terms=extra_terms)

    if as_of:
        query = f"{query} before:{as_of:%Y-%m-%d}"

    search_url = "https://duckduckgo.com/html/"
    params = {"q": query, "kl": "us-en"}
    headers = {"User-Agent": "Mozilla/5.0"}

    if any(t.lower() in {"news","policy","regulation","macro","exchange","update","updates"} for t in (aspects or []) + (extra_terms or [])):
        params["ia"] = "news"

    try:
        r = requests.get(search_url, params=params, headers=headers, timeout=12)
        r.raise_for_status()
    except Exception as exc:
        return {
            "symbol": symbol,
            "query": query,
            "context": f"Web search unavailable: {exc}",
            "results": []
        }

    matches: List[Dict[str, Any]] = []

    for block in r.text.split('<a rel="nofollow" class="result__a"'):
        if "href=" not in block:
            continue

        title_m = re.search(r">(.*?)<", block, re.S)
        url_m = re.search(r'href="(.*?)"', block)
        snippet_m = re.search(r'<a class="result__snippet"(.*?)>(.*?)</a>', block, re.S)

        if title_m and url_m:
            title = re.sub(r"<.*?>", "", title_m.group(1)).strip()
            snippet = re.sub(r"<.*?>", "", snippet_m.group(2)).strip() if snippet_m else ""
            
            # Clean and decode DuckDuckGo redirect link
            real_url = _clean_ddg_url(url_m.group(1))

            matches.append({
                "title": title,
                "url": real_url,
                "snippet": snippet
            })

    aspect_terms = [t for t in (aspects or []) + (extra_terms or []) if t]
    enriched = []

    for m in matches:
        published_at = _naive_datetime(
            extract_datetime_from_text(m.get("snippet","")) or
            extract_datetime_from_text(m.get("title","")) or
            extract_datetime_from_url(m.get("url",""))
        )

        domain = _get_domain(m.get("url",""))
        if domain in WHALE_DOMAINS and not published_at:
            published_at = datetime.utcnow()

        if require_published_at and not published_at:
            continue

        if as_of and published_at and published_at > as_of:
            continue
        if enrich_results and any(domain == d or domain.endswith("." + d) for d in PRIORITY_DOMAINS | WHALE_DOMAINS):
            scraped = scrape_full_page(m.get("url"))
            if scraped:
                extracted = extract_useful_info(scraped, symbol)
                if extracted:
                    m["snippet"] = extracted

        recency_score = compute_recency_score(published_at, reference_time=as_of)
        base_score = _score_result(m, symbol, aspect_terms, additional_priority_domains)
        trade_score = score_trading_importance(m.get("snippet", ""), symbol)
        final_score = base_score + recency_score + trade_score

        enriched.append({
            **m,
            "score": final_score,
            "base_score": base_score,
            "recency_score": recency_score,
            "published_at": published_at.isoformat() if published_at else None
        })

    enriched = [x for x in enriched if x["score"] >= 0]
    enriched.sort(key=lambda x: x["score"], reverse=True)

    dedup: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for item in enriched:
        u = item.get("url","")
        if not u or u in seen:
            continue
        seen.add(u)
        dedup.append(item)
        if len(dedup) >= max_results:
            break

    return {
        "symbol": symbol,
        "query": query,
        "context": format_web_search_results(symbol, dedup),
        "results": dedup
    }