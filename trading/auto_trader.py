# -*- coding: utf-8 -*-
"""
Auto trader - automatically execute simulated trades based on signals
"""
import sys
import pathlib
from datetime import datetime

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import STRATEGY_CONFIG, SECTOR_ETFS
from src.strategy.signal import SignalGenerator
from trading.portfolio import (
    load_portfolio, save_portfolio, load_trades, save_trade,
    get_current_prices, calc_portfolio_value, Position
)


def run_auto_trade():
    """Run one cycle of signal-based auto trading"""
    data_file = ROOT / "sector_data.csv"
    if not data_file.exists():
        print("  No data file found. Run fetch first.")
        return

    panel = pd.read_csv(data_file, parse_dates=["date"])
    if len(panel) < 60:
        print(f"  Not enough data: {len(panel)} rows")
        return

    # Generate signals
    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)
    if signals.empty:
        print("  No signals generated")
        return

    buy_list = signals[signals["signal"] == "buy"].index.tolist()
    sell_list = signals[signals["signal"] == "sell"].index.tolist()
    prices = get_current_prices()
    portfolio = load_portfolio()

    print(f"  Cash: {portfolio.cash:.2f}")
    print(f"  Positions: {len(portfolio.positions)}")
    print(f"  Buy: {buy_list}")
    print(f"  Sell: {sell_list}")

    # === Step 1: Sell ===
    for sector in sell_list:
        if sector in portfolio.positions:
            pos = portfolio.positions[sector]
            price = prices.get(sector)
            if price is None or price <= 0:
                continue
            proceeds = pos.shares * price
            pnl = proceeds - pos.total_cost
            portfolio.cash += proceeds
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "sell",
                "sector": sector,
                "etf_code": SECTOR_ETFS.get(sector, ""),
                "price": round(price, 3),
                "shares": round(pos.shares, 0),
                "amount": round(proceeds, 2),
                "pnl": round(pnl, 2),
                "status": "\u6210\u4ea4\uff08\u6a21\u62df\uff09",
                "reason": "sell_signal",
            }
            save_trade(trade)
            del portfolio.positions[sector]
            print(f"  SELL {sector}: {pos.shares:.0f} shares x {price:.3f} = {proceeds:.2f} (PnL: {pnl:.2f})")

    # === Step 2: Buy (up to top 4) ===
    buys_to_execute = [s for s in buy_list if s not in portfolio.positions][:4]
    if buys_to_execute and portfolio.cash > 0:
        capital_per = portfolio.cash / len(buys_to_execute)
        for sector in buys_to_execute:
            price = prices.get(sector)
            if price is None or price <= 0 or price > capital_per:
                continue
            shares = capital_per / price
            cost = capital_per
            portfolio.positions[sector] = Position(
                sector=sector,
                shares=shares,
                avg_cost=price,
                total_cost=cost,
            )
            portfolio.cash -= cost
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "buy",
                "sector": sector,
                "etf_code": SECTOR_ETFS.get(sector, ""),
                "price": round(price, 3),
                "shares": round(shares, 0),
                "amount": round(cost, 2),
                "pnl": 0,
                "status": "\u6210\u4ea4\uff08\u6a21\u62df\uff09",
                "reason": "buy_signal",
            }
            save_trade(trade)
            print(f"  BUY  {sector}: {shares:.0f} shares x {price:.3f} = {cost:.2f}")

    # === Save ===
    save_portfolio(portfolio)
    total_value = calc_portfolio_value(portfolio, prices)
    pnl = total_value - 100000
    pnl_pct = (pnl / 100000) * 100
    print(f"\n  Portfolio: {total_value:.2f} (PnL: {pnl:.2f}, {pnl_pct:.2f}%)")


if __name__ == "__main__":
    run_auto_trade()
