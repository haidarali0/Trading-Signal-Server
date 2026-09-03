import sys
from pathlib import Path

# Make sure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.search import search_web_context


def run_real_web_test(symbol: str):
    print(f"\n=== REAL WEB SEARCH TEST FOR {symbol} ===\n")

    # Perform real search
    res = search_web_context(
        symbol,
        aspects=['news', 'whale', 'transfer'],
        max_results=10
    )
    print("\n--- Query Used ---")
    print(res.get('query'))

    print("\n--- Context Summary ---")
    print(res.get('context'))

    print("\n--- Detailed Results ---")
    for i, item in enumerate(res.get('results', []), start=1):
        print(f"\n[{i}] Title: {item.get('title')}")
        print(f"     URL: {item.get('url')}")
        print(f"     Score: {item.get('score')}")
        print(f"     Published At: {item.get('published_at')}")
        print(f"     Snippet (Extracted Important Parts):")
        snippet = item.get('snippet') or ""
        print(f"       {snippet[:500]}")  # print first 500 chars


if __name__ == "__main__":
    # You can change this to BTCUSDT, ETHUSDT, SOLUSDT, etc.
    run_real_web_test("BTCUSDT")
