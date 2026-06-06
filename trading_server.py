#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quant Trading Terminal - Simulated Trading
Cost:  python trading_server.py
Cost:  http://localhost:5000
"""
import json, sys, pathlib
from datetime import datetime
from flask import Flask, jsonify, request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from config import STRATEGY_CONFIG, SECTOR_ETFS
from src.strategy.signal import SignalGenerator
from trading.portfolio import (
    load_portfolio, save_portfolio, load_trades,
    get_current_prices, calc_portfolio_value, calc_pnl
)
from trading.auto_trader import run_auto_trade

app = Flask(__name__)
DATA_FILE = ROOT / "sector_data.csv"
TEMPLATE_FILE = ROOT / "trading" / "template.html"


def render_page():
    portfolio = load_portfolio()
    prices = get_current_prices()
    total_value = calc_portfolio_value(portfolio, prices)
    pnl_data = calc_pnl(portfolio, prices)
    pnl = total_value - 100000
    pnl_pct = (pnl / 100000) * 100

    signals = []
    if DATA_FILE.exists():
        panel = pd.read_csv(DATA_FILE, parse_dates=["date"])
        if len(panel) >= 60:
            gen = SignalGenerator(STRATEGY_CONFIG)
            sigs = gen.generate_signals(panel)
            if not sigs.empty:
                latest = panel.iloc[-1]
                for sector in sigs.index:
                    row = sigs.loc[sector]
                    signals.append({
                        "name": sector, "score": round(float(row["total"]), 3),
                        "signal": row["signal"],
                        "price": float(latest.get(sector, 0)),
                        "etf_code": SECTOR_ETFS.get(sector, ""),
                    })

    trades = load_trades()[-30:]
    template = TEMPLATE_FILE.read_text("utf-8")

    # Fill template
    html = template.replace("__TIME__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    total_cls = "green" if total_value >= 100000 else "red"
    pnl_cls = "green" if pnl >= 0 else "red"
    html = html.replace("__TOTAL_CLASS__", total_cls)
    html = html.replace("__TOTAL__", f"{total_value:,.2f}")
    html = html.replace("__PNL_CLASS__", pnl_cls)
    html = html.replace("__PNL__", f"{pnl:+,.2f}")
    html = html.replace("__PNL_PCT__", f"{pnl_pct:+.2f}")
    html = html.replace("__CASH__", f"{portfolio.cash:,.0f}")
    html = html.replace("__PENDING__", f"{portfolio.pending_cash:,.0f}")
    html = html.replace("__POS_COUNT__", str(len(portfolio.positions)))
    html = html.replace("__TRADE_COUNT__", str(len(trades)))

    # Positions
    pos_html = ""
    if pnl_data.get("details"):
        for d in pnl_data["details"]:
            pc = "green" if d["pnl"] >= 0 else "red"
            pos_html += f"""<div class="card">
<h3>{d["sector"]}</h3>
<div class="val {pc}">{d["pnl"]:+,.2f}</div>
<div style="font-size:12px;color:#94a3b8">{d["pnl_pct"]}%</div>
<div style="margin-top:8px;font-size:12px;color:#94a3b8">Cost: {d["avg_cost"]} | Cur: {d["current_price"]} | Shares: {d["shares"]}</div>
</div>"""
    else:
        pos_html = '<div class="card"><h3>No Positions</h3><p style="color:#64748b;margin-top:4px;font-size:13px">Run Auto Trade to start trading.</p></div>'
    html = html.replace("__POSITIONS__", pos_html)

    # Signals
    sig_html = ""
    for s in signals:
        sig_html += f"""<div class="row">
<div><span style="font-weight:500">{s["name"]}</span> <span style="color:#64748b">{s["etf_code"]}</span></div>
<div><span style="color:#94a3b8;margin-right:10px">{s["score"]}</span>
<span class="tag tag-{s["signal"]}">{s["signal"].upper()}</span></div>
</div>"""
    if not signals:
        sig_html = '<p style="color:#64748b;font-size:13px;padding:10px">No signals available. Run data fetch first.</p>'
    html = html.replace("__SIGNALS__", sig_html)

    # Trades
    tr_html = ""
    for t in trades:
        tc = "#4ade80" if t["action"] == "buy" else "#f87171"
        ta = "BUY" if t["action"] == "buy" else "SELL"
        pc2 = ""
        pnl_val = t.get("pnl")
        if pnl_val:
            pc2 = "green" if pnl_val > 0 else "red"
        pnl_display = f"{pnl_val:+,.0f}" if pnl_val else "-"
        tr_html += f"""<tr>
<td style="font-size:12px;color:#94a3b8">{t["time"][-8:]}</td>
<td style="color:{tc}">{ta}</td>
<td>{t["sector"]}</td><td>{t["etf_code"]}</td>
<td>{t["price"]}</td><td>{int(t.get("shares",0))}</td>
<td>{t["amount"]:,.0f}</td>
<td style="color:{pc2}">{pnl_display}</td>
<td style="font-size:12px;color:#64748b">{t.get("reason","-")}</td>
</tr>"""
    if not trades:
        tr_html = '<tr><td colspan="9" style="color:#64748b;text-align:center;padding:20px">No trades yet. Run Auto Trade to begin.</td></tr>'
    html = html.replace("__TRADES__", tr_html)

    return html


@app.route("/")
def index():
    return render_page()


@app.route("/auto_trade", methods=["POST"])
def auto_trade():
    run_auto_trade()
    return '<script>window.location.href="/"</script>'


@app.route("/reset")
def reset():
    for f in ["portfolio.json", "trades.json"]:
        p = ROOT / f
        if p.exists():
            p.unlink()
    return '<script>window.location.href="/"</script>'


@app.route("/api/pnl_history")
def pnl_history():
    trades = load_trades()
    if not trades:
        return jsonify({"data": []})
    history = [{"date": trades[0]["time"][:10], "value": 100000}]
    value = 100000
    for t in trades:
        if t["action"] == "buy":
            value -= t["amount"]
        else:
            value += t["amount"]
        history.append({"date": t["time"][:10], "value": round(value, 2)})
    return jsonify({"data": history})


@app.route("/api/portfolio")
def api_portfolio():
    portfolio = load_portfolio()
    prices = get_current_prices()
    return jsonify({
        "cash": portfolio.cash,
        "total_value": calc_portfolio_value(portfolio, prices),
        "pnl": calc_pnl(portfolio, prices),
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  Quant Trading Terminal - Simulated Trading")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print(f"  http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
