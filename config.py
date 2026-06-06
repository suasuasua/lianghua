# -*- coding: utf-8 -*-
"""
Configuration: Sector ETF list and parameters
"""
from dataclasses import dataclass, field
from typing import Dict, List


SECTOR_ETFS = {
    # === 原板块 (12个) ===
    "Medical": "512010.SH",
    "NewEnergy": "515700.SH",
    "Military": "512660.SH",
    "Securities": "512880.SH",
    "Banking": "512800.SH",
    "RealEstate": "512200.SH",
    "Metals": "512400.SH",
    "Coal": "515220.SH",
    "Telecom": "515880.SH",
    "Media": "512980.SH",
    "Semicon": "512480.SH",
    "Dividend": "510880.SH",

    # === 新增板块 (12个) ===
    "Consumer50": "515650.SH",      # 消费50 (替换原159928.SZ)
    "Tech50": "515750.SH",          # 科技50 (替换原515000.SH)
    "FoodBeverage": "515170.SH",    # 食品饮料
    "Solar": "515790.SH",           # 光伏
    "RareEarth": "516150.SH",       # 稀土
    "ElectricPower": "562350.SH",   # 电力
    "AI": "515070.SH",             # 人工智能
    "Gaming": "516010.SH",         # 游戏
    "BioMedical": "512290.SH",     # 生物医药
    "STAR50": "588000.SH",         # 科创50
    "HKTech": "513180.SH",         # 恒生科技
    "ChinaInternet": "513050.SH",  # 中概互联
}


@dataclass
class StrategyConfig:
    """Strategy parameter configuration"""
    lookback_days: int = 120
    var_max_lags: int = 8
    granger_alpha: float = 0.05
    top_n_buy: int = 4
    bottom_n_sell: int = 4
    signal_threshold: float = 0.6
    coint_entry_z: float = 2.0
    coint_exit_z: float = 0.5


@dataclass
class DataConfig:
    """Data configuration"""
    history_days: int = 300
    cache_dir: str = "./cache"
    sector_etfs: Dict[str, str] = field(default_factory=lambda: SECTOR_ETFS)


DATA_CONFIG = DataConfig()
STRATEGY_CONFIG = StrategyConfig()
