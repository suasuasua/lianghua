# -*- coding: utf-8 -*-
"""Backtesting engine with T+1 settlement awareness"""
from dataclasses import dataclass
from typing import Dict, List
import numpy as np
import pandas as pd
from config import STRATEGY_CONFIG
from src.strategy.signal import SignalGenerator

@dataclass
class TradeRecord:
    date: str
    action: str
    sector: str
    price: float
    shares: float = 0.0
    cost: float = 0.0
    pnl: float = 0.0

class BacktestEngine:
    """Sector rotation backtester with T+1 settlement delay"""

    def __init__(self, config=None, initial_capital: float = 100000.0):
        self.config = config or STRATEGY_CONFIG
        self.signal_gen = SignalGenerator(config)
        self.initial_capital = initial_capital
        self.trades: List[TradeRecord] = []
        self._max_positions = 5

    def run(self, panel: pd.DataFrame, lookback: int = None) -> pd.DataFrame:
        lookback = lookback or self.config.lookback_days
        min_rows = lookback + 60
        if len(panel) < min_rows:
            raise ValueError(f"Not enough data: need {min_rows}, got {len(panel)}")
        self.trades = []
        rebalance_dates = list(range(lookback, len(panel), 20))
        if rebalance_dates[-1] != len(panel) - 1:
            rebalance_dates.append(len(panel) - 1)
        positions: Dict[str, float] = {}
        cash = self.initial_capital
        pending_cash = 0.0

        for idx in rebalance_dates:
            # T+1: settle previous pending cash
            cash += pending_cash
            pending_cash = 0.0
            train_panel = panel.iloc[:idx + 1]
            signals = self.signal_gen.generate_signals(train_panel)
            if signals.empty:
                continue
            current_date = panel.iloc[idx]['date']
            current_prices = panel.iloc[idx]
            buy_list = signals[signals['signal'] == 'buy'].index.tolist()
            sell_list = signals[signals['signal'] == 'sell'].index.tolist()

            # Sell: proceeds go to pending_cash (T+1)
            for sector in sell_list:
                if sector not in positions:
                    continue
                price = float(current_prices[sector])
                shares = positions.pop(sector)
                proceeds = shares * price
                pending_cash += proceeds
                self.trades.append(TradeRecord(date=str(current_date), action='sell', sector=sector, price=price, shares=shares, pnl=proceeds))

            # Buy: use only settled cash
            current_count = len(positions)
            slots_left = self._max_positions - current_count
            if slots_left > 0 and cash > 0:
                new_buys = [s for s in buy_list if s not in positions][:slots_left]
                if len(new_buys) < slots_left:
                    hold_ranks = signals[signals['signal'] == 'hold'].index.tolist()
                    extras = [s for s in hold_ranks if s not in positions][:slots_left - len(new_buys)]
                    new_buys.extend(extras)
                if new_buys:
                    capital_per = cash / len(new_buys)
                    for sector in new_buys:
                        price = float(current_prices[sector])
                        if price > 0 and price <= capital_per:
                            shares = capital_per / price
                            positions[sector] = shares
                            cash -= capital_per
                            self.trades.append(TradeRecord(date=str(current_date), action='buy', sector=sector, price=price, shares=shares, cost=capital_per))

        # Close all positions at end
        final_prices = panel.iloc[-1]
        for sector, shares in list(positions.items()):
            price = float(final_prices[sector])
            proceeds = shares * price
            cash += proceeds
            self.trades.append(TradeRecord(date=str(final_prices['date']), action='close', sector=sector, price=price, shares=shares, pnl=proceeds))
        return self._summary(panel)

    def _compute_nav_series(self, panel: pd.DataFrame) -> pd.Series:
        nav_series = pd.Series(index=panel['date'], dtype=float)
        cash = self.initial_capital
        positions: Dict[str, float] = {}
        trade_idx = 0
        for i in range(len(panel)):
            date = panel.iloc[i]['date']
            while trade_idx < len(self.trades) and self.trades[trade_idx].date == str(date):
                t = self.trades[trade_idx]
                if t.action == 'buy':
                    cash -= t.cost
                    positions[t.sector] = t.shares
                elif t.action in ('sell', 'close'):
                    if t.sector in positions:
                        cash += t.pnl
                        del positions[t.sector]
                trade_idx += 1
            pos_value = sum(shares * float(panel.iloc[i][sector]) for sector, shares in positions.items())
            nav_series.iloc[i] = cash + pos_value
        return nav_series

    def _summary(self, panel: pd.DataFrame) -> pd.DataFrame:
        nav = self._compute_nav_series(panel)
        final_equity = nav.iloc[-1]
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        peak = nav.cummax()
        drawdown = (nav - peak) / peak
        max_dd = drawdown.min() * 100
        daily_returns = nav.pct_change().dropna()
        sharpe = 'N/A'
        if len(daily_returns) > 10 and daily_returns.std() > 0:
            s = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
            sharpe = round(s, 2)
        win_rate = 'N/A'
        sell_trades = [t for t in self.trades if t.action in ('sell', 'close') and t.pnl > 0]
        all_close = [t for t in self.trades if t.action in ('sell', 'close')]
        if all_close:
            win_rate = round(len(sell_trades) / len(all_close) * 100, 1)
        return pd.DataFrame({
            'initial_capital': [self.initial_capital],
            'final_equity': [round(final_equity, 2)],
            'total_return_pct': [round(total_return, 2)],
            'max_drawdown_pct': [round(max_dd, 2)],
            'sharpe_ratio': [sharpe],
            'win_rate_pct': [win_rate],
            'total_trades': [len(self.trades)],
        })