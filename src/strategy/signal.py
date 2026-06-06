# -*- coding: utf-8 -*-
"""
Trading signal generation module
"""
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from config import STRATEGY_CONFIG
from src.analysis.correlation import CorrelationAnalyzer
from src.analysis.rotation import RotationAnalyzer


class SignalGenerator:
    """Combined rotation signal generator"""

    def __init__(self, config=None):
        self.config = config or STRATEGY_CONFIG
        self.corr_analyzer = CorrelationAnalyzer()
        self.rotation = RotationAnalyzer(
            max_lags=self.config.var_max_lags,
            granger_alpha=self.config.granger_alpha,
        )

    def momentum_score(self, panel: pd.DataFrame, lookback: int = None) -> pd.Series:
        """Momentum score: cumulative return over lookback period"""
        lookback = lookback or self.config.lookback_days
        recent = panel.iloc[:, 1:].iloc[-lookback:]
        returns = recent.pct_change().dropna()
        cumulative = (1 + returns).prod() - 1
        return cumulative

    def rotation_score(self, panel: pd.DataFrame) -> pd.Series:
        """Rotation prediction score from VAR model"""
        try:
            forecast = self.rotation.predict_next(panel, steps=5)
            predicted_return = forecast.mean()
            scores = (predicted_return - predicted_return.min()) / (
                predicted_return.max() - predicted_return.min() + 1e-10
            )
            return scores
        except Exception as e:
            print(f"  [WARN] Rotation score failed: {e}")
            return pd.Series(index=panel.columns[1:], dtype=float)

    def strength_score(self, panel: pd.DataFrame) -> pd.Series:
        """Relative strength score"""
        returns = panel.iloc[:, 1:].pct_change().dropna()
        strength = returns.iloc[-20:].mean()
        scores = (strength - strength.min()) / (
            strength.max() - strength.min() + 1e-10
        )
        return scores

    def generate_signals(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Combined signal:
        1. Momentum score (40%)
        2. Rotation prediction (35%)
        3. Relative strength (25%)
        Returns composite scores with buy/sell/hold signals
        """
        if panel.empty or len(panel) < 60:
            return pd.DataFrame()

        momentum = self.momentum_score(panel)
        rotation_pred = self.rotation_score(panel)

        for name in momentum.index:
            if name not in rotation_pred.index:
                rotation_pred[name] = momentum[name]

        strength = self.strength_score(panel)

        combined = pd.DataFrame({
            "momentum": momentum,
            "rotation": rotation_pred,
            "strength": strength,
        })

        combined["total"] = (
            combined["momentum"] * 0.40
            + combined["rotation"] * 0.35
            + combined["strength"] * 0.25
        )

        combined = combined.sort_values("total", ascending=False)

        top_sectors = combined.head(self.config.top_n_buy).index.tolist()
        bottom_sectors = combined.tail(self.config.bottom_n_sell).index.tolist()

        combined["signal"] = "hold"
        combined.loc[top_sectors, "signal"] = "buy"
        combined.loc[bottom_sectors, "signal"] = "sell"

        return combined

    def get_pair_trading_signals(self, panel: pd.DataFrame) -> List[Dict]:
        """Pair trading signals based on cointegration"""
        pairs = self.corr_analyzer.find_cointegrated_pairs(panel)
        signals = []
        for pair_info in pairs:
            name_a, name_b = pair_info["pair"]
            series_a = panel[name_a]
            series_b = panel[name_b]
            spread = series_a - series_b * (series_a.std() / series_b.std())
            zscore = (spread - spread.mean()) / spread.std()
            latest_z = zscore.iloc[-1]
            entry_z = self.config.coint_entry_z
            exit_z = self.config.coint_exit_z

            action = "none"
            if latest_z > entry_z:
                action = f"short {name_a} / long {name_b}"
            elif latest_z < -entry_z:
                action = f"long {name_a} / short {name_b}"
            elif abs(latest_z) < exit_z:
                action = "close"

            signals.append({
                "pair": f"{name_a} - {name_b}",
                "zscore": round(float(latest_z), 2),
                "action": action,
            })
        return signals
