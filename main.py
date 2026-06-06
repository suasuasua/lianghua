#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Board Rotation Quantitative Trading Tool - Main Entry
"""
import argparse
import sys
from datetime import datetime

from config import DATA_CONFIG, STRATEGY_CONFIG
from src.data.fetcher import DataFetcher


def cmd_fetch(args):
    """Download sector ETF data"""
    print("=== Downloading Sector ETF Data ===")
    fetcher = DataFetcher()
    panel = fetcher.build_price_panel(days=args.days or DATA_CONFIG.history_days)
    if panel.empty:
        print("  [ERROR] No data fetched!")
        return

    output = args.output or "sector_data.csv"
    panel.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\n  Saved {len(panel)} rows x {len(panel.columns)-1} sectors to {output}")
    print(f"  Date range: {panel['date'].iloc[0].date()} ~ {panel['date'].iloc[-1].date()}")


def cmd_analyze(args):
    """Analyze sector relationships"""
    import pandas as pd
    from src.analysis.correlation import CorrelationAnalyzer
    from src.analysis.rotation import RotationAnalyzer

    print("=== Sector Relationship Analysis ===")
    data_file = args.data or "sector_data.csv"
    panel = pd.read_csv(data_file, parse_dates=["date"])
    print(f"  Loaded {len(panel)} rows")

    corr = CorrelationAnalyzer()
    corr_matrix = corr.pearson_correlation(panel)
    print("\n--- Correlation Matrix (Top 5) ---")
    print(corr_matrix.round(3))

    print("\n--- Cointegrated Pairs ---")
    pairs = corr.find_cointegrated_pairs(panel)
    if pairs:
        for p in pairs[:10]:
            print(f"  {p['pair'][0]} <-> {p['pair'][1]}  (p-value={p['pvalue']:.4f})")
    else:
        print("  No cointegrated pairs found")

    print("\n--- Granger Causality (Top 8) ---")
    rot = RotationAnalyzer(
        max_lags=STRATEGY_CONFIG.var_max_lags,
        granger_alpha=STRATEGY_CONFIG.granger_alpha,
    )
    causal = rot.get_causal_network(panel, top_k=8)
    for c in causal:
        arrow = "=>" if c["strength"] > 1.3 else "->"
        print(f"  {c['cause']} {arrow} {c['effect']}  (strength={c['strength']:.2f})")


def cmd_signal(args):
    """Generate trading signals"""
    import pandas as pd
    from src.strategy.signal import SignalGenerator

    print("=== Sector Rotation Signals ===")
    data_file = args.data or "sector_data.csv"
    panel = pd.read_csv(data_file, parse_dates=["date"])
    print(f"  Loaded {len(panel)} rows, {len(panel.columns)-1} sectors")

    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)

    if signals.empty:
        print("  [ERROR] Could not generate signals")
        return

    print("\n--- Signal Ranking ---")
    print(signals[["total", "signal"]].round(3).to_string())

    print("\n--- Pair Trading Signals ---")
    pair_signals = gen.get_pair_trading_signals(panel)
    for ps in pair_signals:
        print(f"  {ps['pair']}: z={ps['zscore']} -> {ps['action']}")


def cmd_backtest(args):
    """Backtest strategy"""
    import pandas as pd
    from src.backtest.engine import BacktestEngine

    print("=== Strategy Backtest ===")
    data_file = args.data or "sector_data.csv"
    panel = pd.read_csv(data_file, parse_dates=["date"])
    print(f"  Loaded {len(panel)} rows, {len(panel.columns)-1} sectors")

    engine = BacktestEngine(
        config=STRATEGY_CONFIG,
        initial_capital=args.capital or 100000,
    )
    try:
        result = engine.run(panel)
        print("\n--- Backtest Results ---")
        for col in result.columns:
            print(f"  {col}: {result[col].iloc[0]}")
    except ValueError as e:
        print(f"  [ERROR] {e}")


def cmd_run(args):
    """One-click pipeline: download -> analyze -> signal -> backtest"""
    print("=" * 50)
    print("Sector Rotation Quantitative Trading - Auto Pipeline")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    print("\n[Step 1/4] Downloading data...")
    fetcher = DataFetcher()
    panel = fetcher.build_price_panel(days=args.days or DATA_CONFIG.history_days)
    if panel.empty:
        print("  [ERROR] No data")
        return

    out = args.output or "sector_data.csv"
    panel.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  Done: {len(panel)} rows saved")

    print("\n[Step 2/4] Analyzing sector relationships...")
    from src.analysis.correlation import CorrelationAnalyzer
    from src.analysis.rotation import RotationAnalyzer
    corr = CorrelationAnalyzer()
    corr_matrix = corr.pearson_correlation(panel)
    print("  Correlation matrix computed")
    rot = RotationAnalyzer()
    causal = rot.get_causal_network(panel, top_k=6)
    print("  Granger causality computed")

    print("\n[Step 3/4] Generating signals...")
    from src.strategy.signal import SignalGenerator
    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)
    if not signals.empty:
        print("  Signals generated")
        print("\n  Top Sectors to Buy:")
        for s in signals[signals["signal"] == "buy"].index:
            print(f"    + {s}")
        print("  Sectors to Sell:")
        for s in signals[signals["signal"] == "sell"].index:
            print(f"    - {s}")

    print("\n[Step 4/4] Running backtest...")
    from src.backtest.engine import BacktestEngine
    engine = BacktestEngine(STRATEGY_CONFIG)
    try:
        result = engine.run(panel)
        print("\n  === Backtest Results ===")
        for col in result.columns:
            val = result[col].iloc[0]
            suffix = "%" if "pct" in col else ""
            extra = " OK" if "return" in col and val > 0 else ""
            print(f"    {col}: {val}{suffix}{extra}")
    except ValueError as e:
        print(f"  {e}")

    print("\n" + "=" * 50)
    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Sector Rotation Quantitative Trading Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--days", type=int, help="History days")
    parser.add_argument("--data", type=str, help="Data file path")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--capital", type=float, help="Initial capital")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("fetch", help="Download sector ETF data")
    sub.add_parser("analyze", help="Analyze sector correlations & causality")
    sub.add_parser("signal", help="Generate buy/sell signals")
    sub.add_parser("backtest", help="Backtest the rotation strategy")
    sub.add_parser("run", help="Run full pipeline (fetch -> analyze -> signal -> backtest)")

    args = parser.parse_args()

    commands = {
        "fetch": cmd_fetch,
        "analyze": cmd_analyze,
        "signal": cmd_signal,
        "backtest": cmd_backtest,
        "run": cmd_run,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
