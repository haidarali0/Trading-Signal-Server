import json
import argparse
from typing import List

from engine.llm import build_llm_market_input, inference
from crypto_data.getter import get_candles, get_market_snapshot, Config
from engine.plot import plot_data
from crypto_data.indicators import calculate_indicators
from helper.utils import send_telegram_message, calculate_ratios, format_minimal_pro
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DEFAULT_SYMBOLS, DEFAULT_LIMIT, DEFAULT_INTERVAL,
    DEFAULT_SEND_VALUES, DEFAULT_HIGHER_TIMEFRAMES,
    DEFAULT_INDICATORS, DEFAULT_N,
    CONFIDENCE_THRESHOLD, GAIN_RATIO_THRESHOLD
)


def parse_arguments():
    """Parse command line arguments for the trading analysis system."""
    parser = argparse.ArgumentParser(
        description="Trading View Analysis System - Analyze cryptocurrency markets using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # Run with default symbols
  python main.py -s BTCUSDT ETHUSDT                 # Analyze specific symbols
  python main.py --interval 4h --limit 500          # Custom timeframe and data limit
  python main.py --dry-run                          # Test without sending Telegram messages
        """
    )

    parser.add_argument(
        '-s', '--symbols',
        nargs='+',
        default=DEFAULT_SYMBOLS,
        help=f'Symbols to analyze (default: {DEFAULT_SYMBOLS})'
    )

    parser.add_argument(
        '--interval',
        default=DEFAULT_INTERVAL,
        help=f'Main timeframe interval (default: {DEFAULT_INTERVAL})'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=DEFAULT_LIMIT,
        help=f'Number of candles to fetch (default: {DEFAULT_LIMIT})'
    )

    parser.add_argument(
        '--higher-timeframes',
        nargs='+',
        default=DEFAULT_HIGHER_TIMEFRAMES,
        help=f'Higher timeframe intervals (default: {DEFAULT_HIGHER_TIMEFRAMES})'
    )

    parser.add_argument(
        '--indicators',
        nargs='+',
        default=DEFAULT_INDICATORS,
        help=f'Indicator columns to include (default: {DEFAULT_INDICATORS})'
    )

    parser.add_argument(
        '--confidence-threshold',
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f'Minimum confidence threshold for signals (default: {CONFIDENCE_THRESHOLD})'
    )

    parser.add_argument(
        '--gain-ratio-threshold',
        type=float,
        default=GAIN_RATIO_THRESHOLD,
        help=f'Minimum gain ratio threshold (default: {GAIN_RATIO_THRESHOLD})'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run analysis without sending Telegram messages'
    )

    parser.add_argument(
        '--iterations',
        type=int,
        default=2,
        help='Number of analysis iterations per symbol (default: 2)'
    )

    return parser.parse_args()


# ============================
# MAIN LOOP
# ============================
def run_analysis(symbols: List[str], args) -> None:
  llm_res = None
  crypto_res = {s:[] for s in symbols}
  try:
    for symbol in symbols:
     for _ in range(args.iterations):
        print("====================================")
        print(f"Analyzing {symbol}")
        Config.SYMBOL = symbol
        Config.LIMIT = args.limit
        Config.INTERVAL = args.interval
        basic_interval = Config.INTERVAL
        Config.HIGHER_TIMEFRAMES = args.higher_timeframes
        N = DEFAULT_N

        # Get main timeframe data
        df = get_candles()
        indicators = calculate_indicators(df, args.indicators)
        snapshot = get_market_snapshot(df)

        # Fetch higher timeframe candles
        higher_tf_data = {}
        for tf in Config.HIGHER_TIMEFRAMES:
            Config.INTERVAL = tf
            df_tf = get_candles()
            higher_tf_data[tf] = {"candles": df_tf}

        # Prepare LLM input
        market_info = build_llm_market_input(
            Config.SYMBOL, basic_interval, df, snapshot,
            n=N, indicators=indicators, higher_tf=higher_tf_data
        )

        # Save request for reference
        with open("cache/request.json", "w") as f:
            json.dump(json.loads(market_info), f, indent=2)
            print("✔ Request saved!")

        # LLM inference
        res = inference(market_info, Config.SYMBOL, basic_interval)
        llm_res = res
        crypto_res[Config.SYMBOL].append(res['scenario'].lower().strip())
        print(f"LLM response for {Config.SYMBOL}: {res}")
        if len(crypto_res[Config.SYMBOL]) < 2:
              print(f"Not enough signals for {Config.SYMBOL}, skipping...")
              continue
        elif any(["no_trade"==r for r in crypto_res[Config.SYMBOL]]):
              print(f"no_trade {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, skipping...")
              continue
        elif not (all([r == "up" for r in crypto_res[Config.SYMBOL]]) or all([r == "down" for r in crypto_res[Config.SYMBOL]])):
               print(f"Mismtash {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, skipping...")
               continue
        else:
            print(f"Consistent signals {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, proceeding...")
        plot_data(res['target_price'], res['stop_loss'],  res['expected_time'], basic_interval, symbol)
        print("✔ Chart image saved!")
        try:
            res |= calculate_ratios(res)
        except ValueError as e:
            print("===========================")
            print(e)
            continue

        # Send Telegram if signal strong enough
        if res['confidence'] >= args.confidence_threshold and res["gain_ratio"] >= args.gain_ratio_threshold:
            if not args.dry_run:
                res['Symbol'] = Config.SYMBOL
                msg = format_minimal_pro(res)
                send_telegram_message(msg)
                print("📤 Signal sent to Telegram!")
            else:
                print("📋 DRY RUN: Would send signal to Telegram")
                print(res)
        else:
            print("📊 Signal below thresholds:")
            print(res)
  except Exception as e:
      print(f"error {e}")

if __name__ == "__main__":
    args = parse_arguments()
    print("🚀 Starting Trading View Analysis System")
    print(f"📊 Symbols: {args.symbols}")
    print(f"⏰ Interval: {args.interval}")
    print(f"📈 Limit: {args.limit}")
    print(f"🧾 Indicators: {args.indicators}")
    print(f"🔄 Iterations: {args.iterations}")
    if args.dry_run:
        print("🔍 DRY RUN MODE - No Telegram messages will be sent")
    print("=" * 50)
    run_analysis(args.symbols, args)