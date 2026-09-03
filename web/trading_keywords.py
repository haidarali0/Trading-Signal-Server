# trading_keywords.py
import re

HIGH_IMPACT = [
    "sec", "lawsuit", "regulation", "ban", "investigation", "enforcement",
    "approval", "rejection", "inflation", "interest rate", "fed", "cpi",
    "fomc", "recession", "unemployment", "delist", "listing", "hack",
    "exploit", "outage", "withdrawal freeze", "whale", "large transfer",
    "on-chain", "etf", "blackrock", "fidelity", "spot etf", "inflow",
    "outflow", "liquidity", "freeze"
]

MEDIUM_IMPACT = [
    "partnership", "upgrade", "roadmap", "mainnet", "testnet", "burn",
    "supply", "unlock", "funding rate", "liquidation", "open interest",
    "oi", "validator", "staking", "withdrawals", "gas fees", "rollup",
    "l2", "tps"
]

LOW_IMPACT = [
    "price analysis", "market update", "technical analysis", "prediction",
    "sentiment", "forecast", "trend"
]

NEGATIVE_SENTIMENT = [
    "crash", "dump", "bearish", "fear", "uncertainty", "risk",
    "liquidation", "exploit", "hack", "selloff"
]

POSITIVE_SENTIMENT = [
    "bullish", "rally", "breakout", "surge", "pump", "inflow",
    "accumulation", "buying"
]

SYMBOL_KEYWORDS = {
    "BTC": ["etf", "mining", "halving", "hash rate", "difficulty"],
    "ETH": ["staking", "withdrawals", "gas", "l2", "rollup", "sharding"],
    "SOL": ["outage", "tps", "validator", "runtime", "solana"],
    "XRP": ["sec", "lawsuit", "ruling", "court", "legal"],
    "BNB": ["binance", "bsc", "exploit", "bridge"],
    "ADA": ["cardano", "hydra", "staking"],
    "DOGE": ["elon", "musk", "dogecoin"],
    "AVAX": ["subnet", "avalanche"],
    "DOT": ["polkadot", "parachain"],
    "MATIC": ["polygon", "zk", "rollup"]
}

PRIORITY_DOMAINS = {
    "bitcoinmagazine.com",
    "blockchain.watch",
    "bloomberg.com",
    "clankapp.com",
    "cnbc.com",
    "coindesk.com",
    "coinglass.com",
    "coinmarketcap.com",
    "cointelegraph.com",
    "cryptometer.io",
    "cryptoslate.com",
    "forbes.com",
    "investing.com",
    "marketwatch.com",
    "messari.io",
    "news.bitcoin.com",
    "reuters.com",
    "theblock.co",
    "thedailycoins.io",
}

IGNORED_DOMAINS = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "yahoo.com",
    "search.brave.com"
}

WHALE_DOMAINS = {
    "whale-alert.io",
    "whale-alerts.net",
    "x.com",
    "twitter.com",
    "whale-alert.cam",
    "whalequant.io"
}

NEWS_TERMS = [
    "news", "update", "updates", "breaking", "latest", "today", "analysis", "market"
]

BOILERPLATE_TERMS = {
    "cookie",
    "privacy policy",
    "terms of service",
    "all rights reserved",
    "subscribe",
    "sign up",
    "copyright",
    "advertisement",
    "click here",
    "read more",
    "manage preferences"
}

METRIC_REGEX = re.compile(
    r"(\$\d+(?:\.\d+)?|\b\d+(?:\.\d+)?%|\b\d+(?:k|m|b|t)\b|\b20\d{2}\b)",
    re.IGNORECASE,
)

# --- DYNAMICALLY MERGED MARKET TERMS ---
# Merges all impact keywords, sentiments, and symbol keywords into one unified lookup set
_all_trading_words = (
    HIGH_IMPACT + MEDIUM_IMPACT + LOW_IMPACT + 
    NEGATIVE_SENTIMENT + POSITIVE_SENTIMENT
)
for _kw_list in SYMBOL_KEYWORDS.values():
    _all_trading_words.extend(_kw_list)

# Additional structural/technical terms not covered above
_extra_market_terms = {"volume", "resistance", "support", "target", "short", "long"}

MARKET_TERMS = {w.lower() for w in _all_trading_words}.union(_extra_market_terms)