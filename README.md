# 板块轮动量化交易工具

基于 A股行业 ETF 的板块轮动量化分析与自动交易信号生成工具。

## 核心理念

> 市场资金在板块间存在可观测的轮动模式——当资金从某些板块撤出时，往往会流入其他板块。

本工具通过以下方法捕捉这种轮动：
1. **Granger 因果检验** — 找出哪些板块的涨跌领先于其他板块
2. **VAR 向量自回归模型** — 预测短期板块收益率走势
3. **协整关系分析** — 发现长期均衡的板块对
4. **动量 + 轮动 + 相对强度** — 综合评分生成买卖信号

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
# 一键全流程（下载 → 分析 → 信号 → 回测）
python main.py run

# 分步执行
python main.py fetch              # 下载行业 ETF 历史数据
python main.py analyze            # 分析板块相关性
python main.py signal             # 生成交易信号
python main.py backtest           # 回测策略

# 指定参数
python main.py fetch --days 300
python main.py backtest --capital 100000
```

## 配置

编辑 `config.py` 可调整：
- `SECTOR_ETFS` — 监控的行业 ETF 列表
- `StrategyConfig` — 策略参数（回看天数、信号阈值等）

## 数据来源

东方财富公开行情 API（无需 API Key）
