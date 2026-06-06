#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地交易服务 — 连接仪表盘信号与实际交易
启动: python trading_server.py
访问: http://localhost:5000
"""
import json
import os
import time
import pathlib
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import Flask, jsonify, render_template_string, request

from config import DATA_CONFIG, STRATEGY_CONFIG, SECTOR_ETFS
from src.strategy.signal import SignalGenerator

app = Flask(__name__)

# === 配置 ===
ROOT = pathlib.Path(__file__).resolve().parent
DATA_FILE = ROOT / "sector_data.csv"
TRADES_FILE = ROOT / "trades.json"
CONFIG_FILE = ROOT / "trading_config.json"

# 默认模拟模式
SIMULATION_MODE = True


# === 交易记录 ===
def load_trades():
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text("utf-8"))
    return []


def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    TRADES_FILE.write_text(json.dumps(trades, ensure_ascii=False, indent=2), "utf-8")


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    return {"broker": "simulation", "mode": "simulation"}


# === 获取最新信号 ===
def get_latest_signals():
    if not DATA_FILE.exists():
        return None, "数据文件不存在，请先运行 python main.py --days 300 fetch"

    panel = pd.read_csv(DATA_FILE, parse_dates=["date"])
    if len(panel) < 60:
        return None, "数据不足（< 60行）"

    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)
    if signals.empty:
        return None, "无法生成信号"

    # 获取最新价格
    latest = panel.iloc[-1]
    prices = {s: float(latest[s]) for s in [c for c in panel.columns if c != "date"]}

    # ETF 代码映射
    etf_codes = {name: symbol for name, symbol in SECTOR_ETFS.items() if name in signals.index}

    result = []
    for sector in signals.index:
        row = signals.loc[sector]
        etf_code = etf_codes.get(sector, "")
        result.append({
            "name": sector,
            "score": round(float(row["total"]), 3),
            "signal": row["signal"],
            "price": prices.get(sector, 0),
            "etf_code": etf_code,
            "action_label": "买入" if row["signal"] == "buy" else ("卖出" if row["signal"] == "sell" else "持有"),
        })
    return result, None


# === 路由 ===

@app.route("/")
def index():
    signals, err = get_latest_signals()
    trades = load_trades()[-20:]  # 最近20笔
    config = load_config()

    # 构建ETF代码到中文名的映射
    etf_names = {v: k for k, v in SECTOR_ETFS.items()}

    html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>量化交易终端</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}
.container{max-width:1200px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}
h2{font-size:16px;margin:20px 0 12px;color:#94a3b8}
.sub{color:#64748b;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{background:#1e293b;border-radius:10px;border:1px solid #334155;padding:16px}
.card .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.card .name{font-weight:600;font-size:15px}
.card .code{color:#64748b;font-size:12px}
.card .price{font-size:20px;font-weight:700;margin:4px 0}
.card .score{font-size:12px;color:#94a3b8}
.badge{display:inline-block;padding:2px 10px;border-radius:8px;font-size:12px;font-weight:600}
.badge-buy{background:#22c55e20;color:#4ade80}
.badge-sell{background:#ef444420;color:#f87171}
.badge-hold{background:#f59e0b20;color:#fbbf24}
.btn{display:block;width:100%;padding:10px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-top:10px;transition:opacity .2s}
.btn:hover{opacity:.8}
.btn-buy{background:#22c55e;color:#fff}
.btn-sell{background:#ef4444;color:#fff}
.btn:disabled{background:#334155;color:#64748b;cursor:not-allowed}
.status-bar{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}
.status-item{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:10px 16px;font-size:13px}
.status-item .label{color:#64748b;font-size:11px}
.status-item .value{color:#4ade80;font-weight:600;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 12px;color:#64748b;font-weight:500;border-bottom:1px solid #334155}
td{padding:8px 12px;border-bottom:1px solid #1e293b}
.toast{position:fixed;bottom:20px;right:20px;background:#1e293b;border:1px solid #334155;padding:12px 20px;border-radius:8px;font-size:13px;display:none;z-index:999}
.mode-tag{font-size:11px;padding:2px 8px;border-radius:4px;background:#f59e0b20;color:#fbbf24;margin-left:8px}
</style>
</head>
<body>
<div class="container">
<h1>量化交易终端 <span class="mode-tag">{{ "模拟模式" if simulation else "实盘模式" }}</span></h1>
<div class="sub">{{ report_time }} ｜ {{ signal_count }} 个板块 ｜ <a href="#" onclick="toggleMode()" style="color:#3b82f6;text-decoration:none">切换模式</a></div>

<div class="status-bar">
<div class="status-item"><div class="label">模式</div><div class="value">{{ "模拟交易" if simulation else "⚠ 实盘交易" }}</div></div>
<div class="status-item"><div class="label">今日信号</div><div class="value">{{ buy_count }} 买 / {{ sell_count }} 卖</div></div>
<div class="status-item"><div class="label">累计交易</div><div class="value">{{ trade_count }} 笔</div></div>
</div>

<div class="grid" id="signal-grid">
{% for s in signals %}
<div class="card" data-sector="{{ s.name }}">
<div class="header">
<div><div class="name">{{ s.name }}</div><div class="code">{{ s.etf_code }}</div></div>
<span class="badge badge-{{ 'buy' if s.signal=='buy' else 'sell' if s.signal=='sell' else 'hold' }}">{{ s.action_label }}</span>
</div>
<div class="price">{{ "%.3f"|format(s.price) }}</div>
<div class="score">综合评分: {{ "%.3f"|format(s.score) }}</div>
{% if s.signal == "buy" %}
<button class="btn btn-buy" onclick="trade('{{ s.name }}','{{ s.etf_code }}','buy')">买入 {{ s.etf_code }}</button>
{% elif s.signal == "sell" %}
<button class="btn btn-sell" onclick="trade('{{ s.name }}','{{ s.etf_code }}','sell')">卖出 {{ s.etf_code }}</button>
{% else %}
<button class="btn" disabled>持有观望</button>
{% endif %}
</div>
{% endfor %}
</div>

<h2>交易记录</h2>
<table>
<tr><th>时间</th><th>操作</th><th>板块</th><th>代码</th><th>价格</th><th>金额</th><th>状态</th></tr>
{% for t in trades %}
<tr>
<td>{{ t.time }}</td>
<td style="color:{{ '#4ade80' if t.action=='buy' else '#f87171' }}">{{ "买入" if t.action=="buy" else "卖出" }}</td>
<td>{{ t.sector }}</td>
<td>{{ t.etf_code }}</td>
<td>{{ "%.3f"|format(t.price) }}</td>
<td>{{ "%.0f"|format(t.amount) }}</td>
<td style="color:{{ '#4ade80' if t.status=='成交' else '#fbbf24' }}">{{ t.status }}</td>
</tr>
{% endfor %}
</table>
{% if not trades %}
<p style="color:#64748b;font-size:13px;margin-top:8px">暂无交易记录</p>
{% endif %}
</div>

<div class="toast" id="toast"></div>

<script>
function trade(sector, etf, action) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = "提交中...";

    fetch("/api/trade", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({sector, etf_code: etf, action, amount: 10000})
    })
    .then(r => r.json())
    .then(d => {
        showToast(d.message);
        if (d.status === "ok") {
            setTimeout(() => location.reload(), 1000);
        } else {
            btn.disabled = false;
            btn.textContent = action === "buy" ? "买入 " + etf : "卖出 " + etf;
        }
    })
    .catch(e => {
        showToast("请求失败: " + e.message);
        btn.disabled = false;
        btn.textContent = action === "buy" ? "买入 " + etf : "卖出 " + etf;
    });
}

function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.style.display = "block";
    setTimeout(() => t.style.display = "none", 3000);
}

function toggleMode() {
    fetch("/api/toggle_mode", {method: "POST"})
    .then(r => r.json())
    .then(d => location.reload());
}
</script>
</body>
</html>
"""

    buy_count = sum(1 for s in signals if s["signal"] == "buy") if signals else 0
    sell_count = sum(1 for s in signals if s["signal"] == "sell") if signals else 0

    return render_template_string(html,
        signals=signals or [],
        trades=trades,
        err=err,
        simulation=SIMULATION_MODE,
        buy_count=buy_count,
        sell_count=sell_count,
        signal_count=len(signals) if signals else 0,
        trade_count=len(load_trades()),
        report_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/api/signals")
def api_signals():
    signals, err = get_latest_signals()
    if err:
        return jsonify({"status": "error", "message": err})
    return jsonify({"status": "ok", "data": signals})


@app.route("/api/trade", methods=["POST"])
def api_trade():
    """执行交易"""
    data = request.get_json()
    sector = data.get("sector")
    etf_code = data.get("etf_code", "")
    action = data.get("action")  # "buy" or "sell"
    amount = float(data.get("amount", 10000))

    if not sector or not action:
        return jsonify({"status": "error", "message": "参数不完整"})

    if SIMULATION_MODE:
        price = 0
        signals, _ = get_latest_signals()
        for s in signals or []:
            if s["name"] == sector:
                price = s["price"]
                break

        trade = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "sector": sector,
            "etf_code": etf_code,
            "price": price,
            "amount": amount,
            "shares": round(amount / price, 0) if price > 0 else 0,
            "status": "成交（模拟）",
        }
        save_trade(trade)
        return jsonify({
            "status": "ok",
            "message": f"[模拟] {action} {sector} {etf_code} 成功！金额: {amount:.0f}",
            "trade": trade,
        })
    else:
        # 实盘模式 — 预留券商API接口
        return jsonify({
            "status": "error",
            "message": "实盘模式尚未配置，请先在 trading_config.json 中设置券商信息",
        })


@app.route("/api/orders")
def api_orders():
    trades = load_trades()
    return jsonify({"status": "ok", "data": trades[-50:]})


@app.route("/api/toggle_mode", methods=["POST"])
def api_toggle_mode():
    global SIMULATION_MODE
    SIMULATION_MODE = not SIMULATION_MODE
    config = load_config()
    config["mode"] = "simulation" if SIMULATION_MODE else "live"
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
    return jsonify({"status": "ok", "mode": config["mode"]})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json()
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return jsonify({"status": "ok"})
    return jsonify({"status": "ok", "data": load_config()})


# === 启动 ===
if __name__ == "__main__":
    config = load_config()
    SIMULATION_MODE = config.get("mode", "simulation") == "simulation"

    print("=" * 50)
    print("  量化交易终端")
    print(f"  模式: {'模拟交易' if SIMULATION_MODE else '实盘交易'}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()
    print(f"  打开浏览器访问:")
    print(f"  http://localhost:5000")
    print()
    print(f"  按 Ctrl+C 停止服务")

    app.run(host="0.0.0.0", port=5000, debug=True)
