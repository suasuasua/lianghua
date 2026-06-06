# -*- coding: utf-8 -*-
"""Portfolio tracker - T+1: sell proceeds tracked as pending_cash"""
import json, pathlib
from dataclasses import dataclass, field, asdict
from typing import Dict
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = ROOT / "portfolio.json"
TRADES_FILE = ROOT / "trades.json"
DATA_FILE = ROOT / "sector_data.csv"

@dataclass
class Position:
    sector: str
    shares: float = 0.0
    avg_cost: float = 0.0
    total_cost: float = 0.0

@dataclass
class Portfolio:
    cash: float = 100000.0
    pending_cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)

def load_portfolio() -> Portfolio:
    if PORTFOLIO_FILE.exists():
        data = json.loads(PORTFOLIO_FILE.read_text("utf-8"))
        p = Portfolio(cash=data.get('cash', 100000), pending_cash=data.get('pending_cash', 0.0))
        for s, pos in data.get('positions', {}).items():
            p.positions[s] = Position(**pos)
        return p
    return Portfolio()

def save_portfolio(p: Portfolio):
    data = {"cash": p.cash, "pending_cash": p.pending_cash,
            "positions": {s: asdict(pos) for s, pos in p.positions.items()}}
    PORTFOLIO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def load_trades() -> list:
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text("utf-8"))
    return []

def save_trade(trade: dict):
    trades = load_trades()
    trades.append(trade)
    TRADES_FILE.write_text(json.dumps(trades, ensure_ascii=False, indent=2), "utf-8")

def get_current_prices() -> Dict[str, float]:
    """Get latest close prices from cached data"""
    if not DATA_FILE.exists():
        return {}
    df = pd.read_csv(DATA_FILE, parse_dates=["date"])
    if df.empty:
        return {}
    latest = df.iloc[-1]
    prices = {}
    for col in df.columns:
        if col != "date":
            prices[col] = float(latest[col])
    return prices

def calc_portfolio_value(p: Portfolio, prices: Dict[str, float]) -> float:
    """Total value = cash + pending_cash + positions market value"""
    pos_value = 0.0
    for sector, pos in p.positions.items():
        price = prices.get(sector, 0)
        pos_value += pos.shares * price
    return p.cash + p.pending_cash + pos_value

def calc_pnl(p: Portfolio, prices: Dict[str, float]) -> dict:
    total_pnl = 0.0
    total_cost = 0.0
    details = []
    for sector, pos in p.positions.items():
        price = prices.get(sector, 0)
        market_value = pos.shares * price
        pnl = market_value - pos.total_cost
        pnl_pct = (pnl / pos.total_cost * 100) if pos.total_cost > 0 else 0
        total_pnl += pnl
        total_cost += pos.total_cost
        details.append({
            "sector": sector,
            "shares": round(pos.shares, 2),
            "avg_cost": round(pos.avg_cost, 3),
            "current_price": round(price, 3),
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    return {
        "total_cost": round(total_cost, 2),
        "total_value": round(total_cost + total_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "details": details,
    }