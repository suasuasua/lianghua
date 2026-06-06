#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a self-contained HTML report with ECharts interactive visualizations.
Output: docs/index.html (for GitHub Pages)
"""
import json
import os
import sys
import pathlib
from datetime import datetime

import numpy as np
import pandas as pd

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from config import DATA_CONFIG, STRATEGY_CONFIG
from src.data.fetcher import DataFetcher
from src.analysis.correlation import CorrelationAnalyzer
from src.analysis.rotation import RotationAnalyzer
from src.strategy.signal import SignalGenerator
from src.backtest.engine import BacktestEngine

OUTPUT_DIR = ROOT / "docs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HTML_TEMPLATE = ROOT / "scripts" / "report_template.html"


def fetch_data(days=300):
    print("  Fetching data...")
    fetcher = DataFetcher()
    panel = fetcher.build_price_panel(days=days)
    if panel.empty:
        print("  ERROR: No data")
        return None
    csv_path = ROOT / "sector_data.csv"
    panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  {len(panel)} rows x {len(panel.columns)-1} sectors")
    return panel


def run_analysis(panel):
    results = {}
    names = [c for c in panel.columns if c != "date"]
    results["sectors"] = names
    results["date_range"] = f"{panel['date'].iloc[0].date()} ~ {panel['date'].iloc[-1].date()}"
    results["num_days"] = len(panel)
    results["report_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    returns = panel[names].pct_change().dropna() * 100
    results["returns"] = {
        "dates": panel["date"].iloc[-len(returns):].astype(str).tolist(),
        "data": {col: returns[col].round(3).tolist() for col in names},
    }
    prices = panel[names]
    norm = prices.div(prices.iloc[0]) * 100
    results["prices"] = {
        "dates": panel["date"].astype(str).tolist(),
        "data": {col: norm[col].round(2).tolist() for col in names},
    }

    print("  Computing correlations...")
    corr = CorrelationAnalyzer()
    corr_matrix = corr.pearson_correlation(panel)
    results["correlation"] = {
        "labels": names,
        "matrix": corr_matrix.round(3).values.tolist(),
    }

    print("  Finding cointegrated pairs...")
    pairs = corr.find_cointegrated_pairs(panel)
    results["cointegrated_pairs"] = [
        {"pair": list(p["pair"]), "pvalue": round(p["pvalue"], 4)}
        for p in pairs
    ]

    print("  Computing Granger causality...")
    rot = RotationAnalyzer(
        max_lags=STRATEGY_CONFIG.var_max_lags,
        granger_alpha=STRATEGY_CONFIG.granger_alpha,
    )
    causal = rot.get_causal_network(panel, top_k=15)
    results["causality"] = [
        {"cause": c["cause"], "effect": c["effect"], "strength": round(c["strength"], 2)}
        for c in causal
    ]

    print("  Generating signals...")
    gen = SignalGenerator(STRATEGY_CONFIG)
    signals = gen.generate_signals(panel)
    if not signals.empty:
        results["signals"] = {
            "rankings": signals["total"].round(3).tolist(),
            "actions": signals["signal"].tolist(),
            "sectors": signals.index.tolist(),
        }
    else:
        results["signals"] = {}

    pair_signals = gen.get_pair_trading_signals(panel)
    results["pair_signals"] = pair_signals

    print("  Running backtest...")
    engine = BacktestEngine(STRATEGY_CONFIG, initial_capital=100000)
    try:
        bt_result = engine.run(panel)
        bt_nav = engine._compute_nav_series(panel)
        results["backtest"] = {
            "metrics": {k: str(v[0]) for k, v in bt_result.to_dict().items()},
            "nav": {
                "dates": bt_nav.index.astype(str).tolist(),
                "values": bt_nav.round(2).tolist(),
            },
        }
    except Exception as e:
        print(f"  Backtest failed: {e}")
        results["backtest"] = {}

    flat_corr = []
    for i, n1 in enumerate(names):
        for j, n2 in enumerate(names):
            if i < j:
                flat_corr.append((n1, n2, corr_matrix.iloc[i, j]))
    flat_corr.sort(key=lambda x: abs(x[2]), reverse=True)
    results["top_correlations"] = [
        {"pair": f"{a}-{b}", "value": round(v, 3)}
        for a, b, v in flat_corr[:10]
    ]

    return results


def build_html(results):
    data_json = json.dumps(results, ensure_ascii=False)
    template = HTML_TEMPLATE.read_text("utf-8")
    html = template.replace("__DATA_JSON__", data_json)
    html = html.replace("__REPORT_DATE__", results["report_date"])
    html = html.replace("__NUM_DAYS__", str(results["num_days"]))
    html = html.replace("__DATE_RANGE__", results["date_range"])
    html = html.replace("__NUM_SECTORS__", str(len(results["sectors"])))
    return html


def main():
    print("=== Sector Rotation Report Generator ===\n")

    csv_path = ROOT / "sector_data.csv"
    panel = None

    if csv_path.exists():
        print("  Loading cached data...")
        try:
            panel = pd.read_csv(csv_path, parse_dates=["date"])
        except Exception:
            pass

    if panel is None or len(panel) < 60:
        panel = fetch_data(days=300)
        if panel is None:
            print("  ERROR: Could not fetch data")
            sys.exit(1)
    else:
        print(f"  Using cached: {len(panel)} rows")

    # Load the HTML template, or create default
    if not HTML_TEMPLATE.exists():
        create_default_template()

    print("  Running analysis...")
    results = run_analysis(panel)

    print("  Generating HTML report...")
    html = build_html(results)

    output_path = OUTPUT_DIR / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"\n  Report saved: {output_path}")
    print(f"  File size: {len(html) / 1024:.0f} KB")


def create_default_template():
    """Create default HTML template if it doesn't exist"""
    template = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>版块轮动量化仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0}
.header{background:linear-gradient(135deg,#1e293b,#0f172a);padding:24px 32px;border-bottom:1px solid #334155}
.header h1{font-size:24px;color:#f1f5f9}
.header .sub{font-size:13px;color:#94a3b8;margin-top:4px}
.header .status{display:inline-block;padding:2px 10px;border-radius:10px;font-size:12px;background:#22c55e20;color:#4ade80;margin-left:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px;max-width:1600px;margin:0 auto}
.card{background:#1e293b;border-radius:12px;border:1px solid #334155;overflow:hidden}
.card-header{padding:14px 20px;border-bottom:1px solid #334155;font-size:14px;font-weight:600;color:#f1f5f9;display:flex;justify-content:space-between;align-items:center}
.card-header .badge{font-size:11px;padding:2px 8px;border-radius:8px;font-weight:500}
.badge-buy{background:#22c55e20;color:#4ade80}
.badge-sell{background:#ef444420;color:#f87171}
.badge-hold{background:#f59e0b20;color:#fbbf24}
.chart-container{width:100%;height:400px}
.chart-container.tall{height:500px}
.chart-container.short{height:300px}
.full-width{grid-column:1/-1}
.signal-table{padding:16px 20px}
.signal-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1e293b;font-size:14px}
.signal-row:last-child{border-bottom:none}
.signal-row .name{font-weight:500}
.signal-row .score{font-size:12px;color:#94a3b8}
.signal-row .action{padding:2px 10px;border-radius:8px;font-size:12px;font-weight:600}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px 20px}
.metric-item{text-align:center}
.metric-item .value{font-size:22px;font-weight:700}
.metric-item .label{font-size:11px;color:#94a3b8;margin-top:2px}
.color-green{color:#4ade80}
.color-red{color:#f87171}
.color-yellow{color:#fbbf24}
.pair-list,.coint-list{padding:12px 20px}
.pair-item,.coint-item{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-bottom:1px solid #1e293b}
.pair-item:last-child,.coint-item:last-child{border-bottom:none}
.footer{text-align:center;padding:20px;color:#475569;font-size:12px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
<h1>版块轮动量化仪表盘 <span class="status">Live</span></h1>
<div class="sub">__REPORT_DATE__ | __NUM_DAYS__交易日 | __DATE_RANGE__ | __NUM_SECTORS__个版块</div>
</div>
<div class="grid" id="app"></div>
<div class="footer">由 GitHub Actions 自动生成 | 数据来源: 腾讯财经 API | 不构成投资建议</div>
<script>
const DATA = __DATA_JSON__;
const COLORS = ['#3b82f6','#22c55e','#ef4444','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6','#e11d48','#a855f7','#0ea5e9','#65a30d','#d946ef','#0284c7','#10b981','#f43f5e','#7c3aed','#0891b2','#d97706','#2563eb'];

function renderApp() {
  const signals = DATA.signals || {};
  const bt = DATA.backtest || {};
  const html = [];

  // Signal Card
  let signalRows = '';
  if (signals.sectors) {
    const buyCount = signals.actions.filter(a => a === 'buy').length;
    signalRows = signals.sectors.map((name, i) => {
      const action = signals.actions[i];
      const cls = action === 'buy' ? 'badge-buy' : action === 'sell' ? 'badge-sell' : 'badge-hold';
      const label = action === 'buy' ? 'BUY' : action === 'sell' ? 'SELL' : 'HOLD';
      return '<div class="signal-row"><span class="name">' + name + '</span><span class="score">' + signals.rankings[i].toFixed(3) + '</span><span class="action ' + cls + '">' + label + '</span></div>';
    }).join('');
    html.push('<div class="card"><div class="card-header">今日交易信号 <span class="badge badge-buy">BUY ' + buyCount + '</span></div><div class="signal-table">' + signalRows + '</div></div>');
  } else {
    html.push('<div class="card"><div class="card-header">今日交易信号</div><div style="padding:20px;color:#64748b;">暂无信号</div></div>');
  }

  // Metrics Card
  if (bt.metrics) {
    const m = bt.metrics;
    const tp = parseFloat(m.total_return_pct);
    const sp = parseFloat(m.sharpe_ratio);
    const items = [
      {v: m.total_return_pct + '%', l: '总收益', c: tp >= 0 ? 'color-green' : 'color-red'},
      {v: m.max_drawdown_pct + '%', l: '最大回撤', c: 'color-red'},
      {v: m.sharpe_ratio, l: '夏普比率', c: sp >= 1 ? 'color-green' : sp >= 0 ? 'color-yellow' : 'color-red'},
      {v: m.final_equity, l: '最终权益', c: 'color-green'},
    ];
    const metricHtml = items.map(x => '<div class="metric-item"><div class="value ' + x.c + '">' + x.v + '</div><div class="label">' + x.l + '</div></div>').join('');
    html.push('<div class="card"><div class="card-header">回测表现</div><div class="metrics">' + metricHtml + '</div><div class="chart-container short" id="nav-chart"></div></div>');
  }

  // Correlation (full width)
  html.push('<div class="card full-width"><div class="card-header">板块相关性矩阵</div><div class="chart-container tall" id="corr-heatmap"></div></div>');

  // Causality (full width)
  html.push('<div class="card full-width"><div class="card-header">Granger因果关系 <span style="font-size:12px;color:#94a3b8;font-weight:400;">原因\u2192结果，线越粗越显著</span></div><div class="chart-container tall" id="causality-graph"></div></div>');

  // Price Trends (full width)
  html.push('<div class="card full-width"><div class="card-header">板块走势对比(基准100)</div><div class="chart-container tall" id="price-chart"></div></div>');

  // Cointegrated Pairs
  const pairs = DATA.cointegrated_pairs || [];
  let cointHtml = pairs.length ? pairs.map(p => '<div class="coint-item"><span>' + p.pair[0] + ' \u2194 ' + p.pair[1] + '</span><span style="color:#94a3b8;">p=' + p.pvalue.toFixed(4) + '</span></div>').join('') : '<div style="padding:12px 20px;color:#64748b;font-size:13px;">未发现显著协整配对</div>';
  html.push('<div class="card"><div class="card-header">协整配对</div><div class="coint-list">' + cointHtml + '</div></div>');

  // Pair Trading Signals
  const pt = DATA.pair_signals || [];
  let ptHtml = pt.length ? pt.map(p => '<div class="pair-item"><span>' + p.pair + '</span><span>z=' + p.zscore + ' \u2192 ' + p.action + '</span></div>').join('') : '<div style="padding:12px 20px;color:#64748b;font-size:13px;">暂无配对信号</div>';
  html.push('<div class="card"><div class="card-header">配对交易信号</div><div class="pair-list">' + ptHtml + '</div></div>');

  document.getElementById('app').innerHTML = html.join('');

  // Now render charts
  if (bt.nav) renderNav(bt.nav);
  renderCorr();
  renderCausality();
  renderPrices();
}

function renderNav(nav) {
  const chart = echarts.init(document.getElementById('nav-chart'));
  chart.setOption({
    grid: {left:'5%',right:'5%',top:15,bottom:20},
    xAxis: {type:'category',data:nav.dates.filter((_,i)=>i%30===0),axisLabel:{fontSize:10,color:'#94a3b8'}},
    yAxis: {type:'value',splitLine:{lineStyle:{color:'#1e293b'}},axisLabel:{fontSize:10,color:'#94a3b8'}},
    series: [{type:'line',data:nav.values,smooth:true,showSymbol:false,lineStyle:{width:2,color:'#4ade80'},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'#4ade8040'},{offset:1,color:'#4ade8005'}]}}}],
    tooltip: {trigger:'axis',valueFormatter:v=>'\xc2\xa5'+v.toFixed(2)}
  });
  window.addEventListener('resize',()=>chart.resize());
}

function renderCorr() {
  const c = DATA.correlation;
  const labels = c.labels;
  const data = [];
  for (let i = 0; i < labels.length; i++) {
    for (let j = 0; j < labels.length; j++) {
      data.push([j, i, c.matrix[i][j]]);
    }
  }
  const chart = echarts.init(document.getElementById('corr-heatmap'));
  chart.setOption({
    grid:{left:'10%',right:'3%',top:10,bottom:'12%'},
    xAxis:{type:'category',data:labels,axisLabel:{rotate:45,fontSize:10,color:'#94a3b8'},splitArea:{show:true}},
    yAxis:{type:'category',data:labels,axisLabel:{fontSize:10,color:'#94a3b8'},splitArea:{show:true}},
    visualMap:{min:-0.5,max:1,inRange:{color:['#1e3a5f','#2563eb','#22c55e','#facc15','#ef4444']},calculable:true,textStyle:{color:'#94a3b8'}},
    series:[{type:'heatmap',data:data,label:{show:false}}],
    tooltip:{formatter:p=>'<b>'+p.value[1]+' x '+p.value[0]+'</b><br/>相关系数: '+p.value[2].toFixed(3)}
  });
  window.addEventListener('resize',()=>chart.resize());
}

function renderCausality() {
  const edges = DATA.causality || [];
  if (!edges.length) return;
  const nodesSet = new Set();
  edges.forEach(e=>{nodesSet.add(e.cause);nodesSet.add(e.effect);});
  const nodes = Array.from(nodesSet).map(n=>({id:n,name:n,symbolSize:14,itemStyle:{color:'#3b82f6'}}));
  const maxStr = Math.max(...edges.map(e=>e.strength));
  const links = edges.map(e=>({source:e.cause,target:e.effect,lineStyle:{width:1+4*(e.strength/maxStr),curveness:0.2,color:'#facc15',opacity:0.5+0.5*(e.strength/maxStr)}}));
  const chart = echarts.init(document.getElementById('causality-graph'));
  chart.setOption({
    series:[{type:'graph',layout:'force',roam:true,draggable:true,data:nodes,links:links,force:{repulsion:300,edgeLength:150},label:{show:true,fontSize:11,color:'#e2e8f0'},lineStyle:{color:'source'}}],
    tooltip:{formatter:p=>'<b>'+(p.data.source||p.data.name)+'</b>'+(p.data.source?' \u2192 <b>'+p.data.target+'</b><br/>强度: '+edges.find(e=>e.cause===p.data.source&&e.effect===p.data.target).strength:'')}
  });
  window.addEventListener('resize',()=>chart.resize());
}

function renderPrices() {
  const p = DATA.prices;
  if (!p) return;
  const chart = echarts.init(document.getElementById('price-chart'));
  const series = DATA.sectors.map((name,i)=>({name,type:'line',data:p.data[name],smooth:true,showSymbol:false,lineStyle:{width:1.5,color:COLORS[i%COLORS.length]}}));
  chart.setOption({
    legend:{top:0,textStyle:{fontSize:11,color:'#94a3b8'},type:'scroll'},
    grid:{left:'3%',right:'3%',top:50,bottom:20},
    xAxis:{type:'category',data:p.dates.filter((_,i)=>i%30===0),axisLabel:{fontSize:10,color:'#94a3b8'}},
    yAxis:{type:'value',splitLine:{lineStyle:{color:'#1e293b'}},axisLabel:{fontSize:10,color:'#94a3b8'}},
    series,
    tooltip:{trigger:'axis'}
  });
  window.addEventListener('resize',()=>chart.resize());
}

renderApp();
</script>
</body>
</html>"""
    HTML_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    HTML_TEMPLATE.write_text(template, encoding="utf-8")
    print("  Created default HTML template")


if __name__ == "__main__":
    main()
