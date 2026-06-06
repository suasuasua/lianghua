#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易终端 — 模拟实盘自动交易 + 组合盈亏看板
启动: python trading_server.py
访问: http://localhost:5000
"""
import json
import sys
import pathlib
from datetime import datetime

from flask import Flask, jsonify, render_template_string, request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import STRATEGY_CONFIG, SECTOR_ETFS
from src.strategy.signal import SignalGenerator
from trading.portfolio import (
    load_portfolio, save_portfolio, load_trades,
    get_current_prices, calc_portfolio_value, calc_pnl
)
from trading.auto_trader import run_auto_trade

app = Flask(__name__)

PORTFOLIO_FILE = ROOT / "portfolio.json"
DATA_FILE = ROOT / "sector_data.csv"


@app.route("/")
def index():
    portfolio = load_portfolio()
    prices = get_current_prices()
    total_value = calc_portfolio_value(portfolio, prices)
    pnl_data = calc_pnl(portfolio, prices)

    # Get latest signals
    signals = []
    if DATA_FILE.exists():
        import pandas as pd
        panel = pd.read_csv(DATA_FILE, parse_dates=["date"])
        if len(panel) >= 60:
            gen = SignalGenerator(STRATEGY_CONFIG)
            sigs = gen.generate_signals(panel)
            if not sigs.empty:
                latest = panel.iloc[-1]
                for sector in sigs.index:
                    row = sigs.loc[sector]
                    etf_code = SECTOR_ETFS.get(sector, "")
                    signals.append({
                        "name": sector,
                        "score": round(float(row["total"]), 3),
                        "signal": row["signal"],
                        "price": float(latest.get(sector, 0)),
                        "etf_code": etf_code,
                    })

    trades = load_trades()[-30:]
    pnl = total_value - 100000
    pnl_pct = (pnl / 100000) * 100

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>\\u91cf\\u5316\\u4ea4\\u6613\\u7ec8\\u7aef<\\/title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;font-size:14px}
.container{max-width:1400px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}
h2{font-size:16px;margin:20px 0 10px;color:#94a3b8}
.sub{color:#64748b;font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{background:#1e293b;border-radius:10px;border:1px solid #334155;padding:16px}
.card h3{font-size:14px;color:#94a3b8;margin-bottom:8px}
.val{font-size:28px;font-weight:700}
.val.green{color:#4ade80}
.val.red{color:#f87171}
.val.yellow{color:#fbbf24}
.tag{display:inline-block;padding:2px 10px;border-radius:8px;font-size:12px;font-weight:600}
.tag-buy{background:#22c55e20;color:#4ade80}
.tag-sell{background:#ef444420;color:#f87171}
.tag-hold{background:#f59e0b20;color:#fbbf24}
.btn{display:inline-block;padding:10px 24px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;text-decoration:none;color:#fff}
.btn-green{background:#22c55e}
.btn-blue{background:#3b82f6}
.btn-red{background:#ef4444}
.btn-sm{padding:4px 12px;font-size:12px;border-radius:4px;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 12px;color:#64748b;font-weight:500;border-bottom:1px solid #334155}
td{padding:8px 12px;border-bottom:1px solid #1e293b}
.row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1e293b;font-size:13px}
.row:last-child{border-bottom:none}
.bar{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.bar-item{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 20px;flex:1;min-width:150px}
.bar-item .l{font-size:11px;color:#64748b}
.bar-item .v{font-size:22px;font-weight:700;margin-top:2px}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<h1>\\u91cf\\u5316\\u4ea4\\u6613\\u7ec8\\u7aef</h1>
<div class="sub">{{ now }} | \\u6a21\\u62df\\u8d44\\u91d1: \\u00a5100,000</div>

<div class="bar">
<div class="bar-item"><div class="l">\\u7ec4\\u5408\\u603b\\u503c</div><div class="v {{ 'green' if total >= init else 'red' }}">\\u00a5{{ "{:,.2f}".format(total) }}</div></div>
<div class="bar-item"><div class="l">\\u603b\\u76c8\\u4e8f</div><div class="v {{ 'green' if pnl >= 0 else 'red' }}">{{ "{:+,.2f}".format(pnl) }} ({{ "{:+.2f}".format(pnl_pct) }}%)</div></div>
<div class="bar-item"><div class="l">\\u73b0\\u91d1</div><div class="v">{{ "{:,.0f}".format(portfolio.cash) }}</div></div>
<div class="bar-item"><div class="l">\\u6301\\u4ed3\\u6570</div><div class="v">{{ portfolio.positions|length }}</div></div>
<div class="bar-item"><div class="l">\\u7d2f\\u8ba1\\u4ea4\\u6613</div><div class="v">{{ trades|length }}</div></div>
</div>

<div style="margin-bottom:16px">
<form action="/auto_trade" method="post" style="display:inline">
<button class="btn btn-green">\\u25b6 \\u6267\\u884c\\u81ea\\u52a8\\u8c03\\u4ed3</button>
</form>
<a href="/reset" class="btn btn-red" style="margin-left:8px;background:#475569" onclick="return confirm('\\u786e\\u5b9a\\u91cd\\u7f6e\\u6a21\\u62df\\u7ec4\\u5408\\u5417\\uff1f')">\\u91cd\\u7f6e\\u6a21\\u62df</a>
</div>

<h2>\\u6301\\u4ed3\\u660e\\u7ec6</h2>
<div class="grid">
{% for d in pnl_data.details %}
<div class="card">
<h3>{{ d.sector }}</h3>
<div class="val {{ 'green' if d.pnl >= 0 else 'red' }}">{{ "{:+,.2f}".format(d.pnl) }}</div>
<div style="font-size:12px;color:#94a3b8">{{ d.pnl_pct }}%</div>
<div style="margin-top:8px;font-size:12px;color:#94a3b8">
\\u6210\\u672c: {{ d.avg_cost }} | \\u5f53\\u524d: {{ d.current_price }} | \\u80a1\\u6570: {{ d.shares }}
</div>
</div>
{% endfor %}
{% if not pnl_data.details %}
<div class="card"><h3>\\u65e0\\u6301\\u4ed3</h3><p style="color:#64748b;margin-top:4px;font-size:13px">\\u70b9\\u51fb\\u201c\\u6267\\u884c\\u81ea\\u52a8\\u8c03\\u4ed3\\u201d\\u5f00\\u59cb\\u6a21\\u62df\\u4ea4\\u6613</p></div>
{% endif %}
</div>

<h2>\\u4fe1\\u53f7\\u6392\\u540d</h2>
{% for s in signals %}
<div class="row">
<div><span style="font-weight:500">{{ s.name }}</span> <span style="color:#64748b">{{ s.etf_code }}</span></div>
<div>
<span style="color:#94a3b8;margin-right:10px">{{ s.score }}</span>
<span class="tag tag-{{ s.signal }}">{{ s.signal|upper }}</span>
</div>
</div>
{% endfor %}

<h2>\\u4ea4\\u6613\\u8bb0\\u5f55</h2>
<table>
<tr><th>\\u65f6\\u95f4</th><th>\\u64cd\\u4f5c</th><th>\\u677f\\u5757</th><th>\\u4ee3\\u7801</th><th>\\u4ef7\\u683c</th><th>\\u80a1\\u6570</th><th>\\u91d1\\u989d</th><th>\\u76c8\\u4e8f</th><th>\\u539f\\u56e0</th></tr>
{% for t in trades %}
<tr>
<td style="font-size:12px;color:#94a3b8">{{ t.time[-8:] }}</td>
<td style="color:{{ '#4ade80' if t.action=='buy' else '#f87171' }}">{{ "\\u4e70\\u5165" if t.action=="buy" else "\\u5356\\u51fa" }}</td>
<td>{{ t.sector }}</td><td>{{ t.etf_code }}</td>
<td>{{ t.price }}</td><td>{{ t.shares|int }}</td>
<td>{{ "{:,.0f}".format(t.amount) }}</td>
<td style="color:{{ 'green' if t.pnl and t.pnl > 0 else 'red' if t.pnl and t.pnl < 0 else '' }}">{{ "{:+,.0f}".format(t.pnl|float) if t.pnl else '-' }}</td>
<td style="font-size:12px;color:#64748b">{{ t.reason if t.reason else '-' }}</td>
</tr>
{% endfor %}
</table>

<h2>\\u5468\\u671f\\u76c8\\u4e8f\\u53d8\\u5316</h2>
<div id="pnl-chart" style="background:#1e293b;border-radius:10px;border:1px solid #334155;height:300px;margin-bottom:20px"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
fetch('/api/pnl_history').then(r=>r.json()).then(d=>{
  if (!d.data || d.data.length < 2) return;
  const chart = echarts.init(document.getElementById('pnl-chart'));
  chart.setOption({
    grid:{left:'5%',right:'5%',top:20,bottom:20},
    xAxis:{type:'category',data:d.data.map(p=>p.date),axisLabel:{fontSize:10,color:'#94a3b8'}},
    yAxis:{type:'value',splitLine:{lineStyle:{color:'#1e293b'}},axisLabel:{fontSize:10,color:'#94a3b8'}},
    series:[
      {name:'\\u7ec4\\u5408\\u503c',type:'line',data:d.data.map(p=>p.value),smooth:true,showSymbol:false,lineStyle:{width:2,color:'#3b82f6'},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'#3b82f640'},{offset:1,color:'#3b82f605'}]}}},
    ],
    tooltip:{trigger:'axis'}
  });
  window.addEventListener('resize',()=>chart.resize());
});
</script>
</body>
</html>"""

    return render_template_string(html,
        portfolio=portfolio,
        total=total_value,
        init=100000,
        pnl=pnl,
        pnl_pct=pnl_pct,
        pnl_data=pnl_data,
        signals=signals,
        trades=trades,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/auto_trade", methods=["POST"])
def auto_trade():
    run_auto_trade()
    return """<script>window.location.href='/'</script>"""


@app.route("/reset")
def reset():
    import os
    for f in ["portfolio.json", "trades.json"]:
        p = ROOT / f
        if p.exists():
            p.unlink()
    return """<script>window.location.href='/'</script>"""


@app.route("/api/pnl_history")
def pnl_history():
    trades = load_trades()
    if not trades:
        return jsonify({"data": []})
    history = []
    value = 100000
    history.append({"date": trades[0]["time"][:10], "value": value})
    for t in trades:
        if t["action"] == "buy":
            value -= t["amount"]
        else:
            value += t["amount"]
        history.append({"date": t["time"][:10], "value": round(value, 2)})
    return jsonify({"data": history})


@app.route("/api/signals")
def api_signals():
    if not DATA_FILE.exists():
        return jsonify({"status": "error", "message": "no data"})
    import pandas as pd
    panel = pd.read_csv(DATA_FILE, parse_dates=["date"])
    if len(panel) < 60:
        return jsonify({"status": "error", "message": "not enough data"})
    gen = SignalGenerator(STRATEGY_CONFIG)
    sigs = gen.generate_signals(panel)
    return jsonify({"status": "ok", "data": sigs.to_dict()})


@app.route("/api/portfolio")
def api_portfolio():
    portfolio = load_portfolio()
    prices = get_current_prices()
    total_value = calc_portfolio_value(portfolio, prices)
    pnl_data = calc_pnl(portfolio, prices)
    return jsonify({
        "cash": portfolio.cash,
        "total_value": total_value,
        "pnl": pnl_data,
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  \\u91cf\\u5316\\u4ea4\\u6613\\u7ec8\\u7aef - \\u6a21\\u62df\\u5b9e\\u76d8")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print(f"  http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
