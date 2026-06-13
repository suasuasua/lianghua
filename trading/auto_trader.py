# -*- coding: utf-8 -*-
"""Auto trader - T+1 aware: sell proceeds go to pending_cash"""
import sys, pathlib
from datetime import datetime
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import STRATEGY_CONFIG, SECTOR_ETFS
from src.strategy.signal import SignalGenerator
from trading.portfolio import load_portfolio, save_portfolio, load_trades, save_trade, get_current_prices, calc_portfolio_value, Position


def run_auto_trade():
    """Run one cycle of signal-based auto trading (T+1 aware)"""
    data_file = ROOT / "sector_data.csv"
    if not data_file.exists():
        print("  No data file found. Run fetch first.")
        return
    panel = pd.read_csv(data_file, parse_dates=['date'])
    if len(panel) < 60:
        print(f"  Not enough data: {len(panel)} rows")
        return
    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)
    if signals.empty:
        print("  No signals generated")
        return
    buy_list = signals[signals['signal'] == 'buy'].index.tolist()
    sell_list = signals[signals['signal'] == 'sell'].index.tolist()
    prices = get_current_prices()
    portfolio = load_portfolio()
    print(f'  Settled Cash: {portfolio.cash:.2f}')
    print(f'  Pending Cash (T+1): {portfolio.pending_cash:.2f}')
    print(f'  Positions: {len(portfolio.positions)}')
    if buy_list:
        print(f'  Buy signals: {buy_list}')
    if sell_list:
        print(f'  Sell signals: {sell_list}')

    # Step 1: Settle pending cash from previous session
    portfolio.cash += portfolio.pending_cash
    portfolio.pending_cash = 0.0

    # Step 2: Stop-loss check - sell positions that hit stop-loss threshold
    stop_loss = getattr(STRATEGY_CONFIG, 'stop_loss_pct', 0.05)
    for sector in list(portfolio.positions.keys()):
        pos = portfolio.positions[sector]
        price = prices.get(sector)
        if price is None or price <= 0:
            continue
        loss_pct = (price - pos.avg_cost) / pos.avg_cost
        if loss_pct <= -stop_loss:
            proceeds = pos.shares * price
            pnl = proceeds - pos.total_cost
            portfolio.pending_cash += proceeds
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "sell",
                "sector": sector,
                "etf_code": SECTOR_ETFS.get(sector, ""),
                "price": round(price, 3),
                "shares": round(pos.shares, 0),
                "amount": round(proceeds, 2),
                "pnl": round(pnl, 2),
                "status": "simulated",
                "reason": "stop_loss",
            }
            save_trade(trade)
            del portfolio.positions[sector]
            print(f"  STOP-LOSS {sector}: {pos.shares:.0f} shares x {price:.3f} = {proceeds:.2f} (loss: {loss_pct*100:.1f}%)")

    # Step 3: Signal-based Sell - proceeds go to pending_cash (T+1)
    for sector in sell_list:
        if sector in portfolio.positions:
            pos = portfolio.positions[sector]
            price = prices.get(sector)
            if price is None or price <= 0:
                continue
            proceeds = pos.shares * price
            pnl = proceeds - pos.total_cost
            portfolio.pending_cash += proceeds
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "sell",
                "sector": sector,
                "etf_code": SECTOR_ETFS.get(sector, ""),
                "price": round(price, 3),
                "shares": round(pos.shares, 0),
                "amount": round(proceeds, 2),
                "pnl": round(pnl, 2),
                "status": "simulated",
                "reason": "sell_signal",
            }
            save_trade(trade)
            del portfolio.positions[sector]
            print(f"  SELL {sector}: {pos.shares:.0f} shares x {price:.3f} = {proceeds:.2f} (PnL: {pnl:.2f}) -> pending")

    # Step 4: Buy - use ONLY settled cash (T+1 proceeds NOT available)
    buys_to_execute = [s for s in buy_list if s not in portfolio.positions][:4]
    if buys_to_execute and portfolio.cash > 0:
        capital_per = portfolio.cash / len(buys_to_execute)
        for sector in buys_to_execute:
            price = prices.get(sector)
            if price is None or price <= 0 or price > capital_per:
                continue
            shares = capital_per / price
            cost = capital_per
            portfolio.positions[sector] = Position(sector=sector, shares=shares, avg_cost=price, total_cost=cost)
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
                "status": "simulated",
                "reason": "buy_signal",
            }
            save_trade(trade)
            print(f"  BUY  {sector}: {shares:.0f} shares x {price:.3f} = {cost:.2f}")

    save_portfolio(portfolio)
    total_value = calc_portfolio_value(portfolio, prices)
    pnl = total_value - 100000
    pnl_pct = (pnl / 100000) * 100
    print(f"\n  Portfolio: {total_value:.2f} (PnL: {pnl:.2f}, {pnl_pct:.2f}%)")
    print(f"  Settled Cash: {portfolio.cash:.2f}, Pending (T+1): {portfolio.pending_cash:.2f}")

if __name__ == "__main__":
    run_auto_trade()

def run_fetch_and_trade() -> dict:
    """Fetch real-time data, then execute auto-trade cycle. Returns status dict."""
    result = {"status": "ok", "message": "", "time": ""}
    from datetime import datetime
    from src.data.fetcher import DataFetcher
    result["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Fetch realtime prices
    print("\n=== Hourly Cycle: Fetching realtime prices ===")
    fetcher = DataFetcher()
    prices = fetcher.fetch_realtime_quotes()
    if not prices:
        result["status"] = "error"
        result["message"] = "Failed to fetch realtime prices"
        return result

    # Step 2: Update sector_data.csv with latest realtime close
    data_file = ROOT / "sector_data.csv"
    if data_file.exists():
        panel = pd.read_csv(data_file, parse_dates=["date"])
        latest_date = panel["date"].iloc[-1]
        today_str = datetime.now().strftime("%Y-%m-%d")
        # Handle both Timestamp and string dates
        if hasattr(latest_date, "strftime"):
            latest_str = latest_date.strftime("%Y-%m-%d")
        else:
            latest_str = str(latest_date)[:10]
        if latest_str == today_str:
            for col in panel.columns:
                if col != "date" and col in prices:
                    panel.iloc[-1, panel.columns.get_loc(col)] = prices[col]
        else:
            new_row = {"date": today_str}
            for col in panel.columns:
                if col != "date":
                    new_row[col] = prices.get(col, panel[col].iloc[-1])
            panel = pd.concat([panel, pd.DataFrame([new_row])], ignore_index=True)
        panel.to_csv(data_file, index=False)

    # Step 3: Run auto-trade with realtime prices
    print("\n=== Executing trades ===")
    run_auto_trade()

    result["message"] = f"Auto-trade completed at {result['time']}"
    return result

run_fetch_and_trade = run_fetch_and_trade
