# -*- coding: utf-8 -*-
"""
Sector rotation analysis - VAR model + Granger causality
"""
import warnings
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests

warnings.filterwarnings("ignore")


class RotationAnalyzer:
    """Capital rotation analysis and prediction"""

    def __init__(self, max_lags: int = 10, granger_alpha: float = 0.05):
        self.max_lags = max_lags
        self.granger_alpha = granger_alpha
        self.var_model = None
        self.var_results = None
        self._lag_order = None

    def _prepare_returns(self, panel: pd.DataFrame) -> pd.DataFrame:
        returns = panel.iloc[:, 1:].pct_change().dropna()
        return returns * 100

    def granger_causality(self, panel: pd.DataFrame) -> pd.DataFrame:
        returns = self._prepare_returns(panel)
        names = returns.columns
        n = len(names)
        matrix = pd.DataFrame(np.zeros((n, n)), index=names, columns=names)
        maxlag = min(self.max_lags, max(1, len(returns) // 5))

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                try:
                    test_result = grangercausalitytests(
                        returns[[names[i], names[j]]],
                        maxlag=maxlag,
                        verbose=False,
                    )
                    min_p = min(
                        test_result[lag][0]["ssr_ftest"][1]
                        for lag in test_result
                    )
                    matrix.iloc[j, i] = -np.log10(min_p + 1e-10)
                except Exception:
                    matrix.iloc[j, i] = 0.0
        return matrix

    def fit_var(self, panel: pd.DataFrame) -> object:
        returns = self._prepare_returns(panel)
        model = VAR(returns)
        n_obs = len(returns)
        maxlag = min(self.max_lags, max(1, n_obs // 5))
        n_vars = len(returns.columns)

        # Estimate safe max lags: need n_obs > maxlag * n_vars + maxlag
        safe_maxlag = min(maxlag, max(1, (n_obs - 1) // (n_vars + 1)))
        if safe_maxlag < 1:
            safe_maxlag = 1

        try:
            lag_order = model.select_order(maxlags=safe_maxlag)
            self._lag_order = lag_order.aic
        except Exception:
            self._lag_order = 1

        if self._lag_order is None or self._lag_order < 1:
            self._lag_order = 1

        self.var_results = model.fit(maxlags=self._lag_order)
        return self.var_results

    def predict_next(self, panel: pd.DataFrame, steps: int = 5) -> pd.DataFrame:
        if self.var_results is None:
            self.fit_var(panel)

        last_obs = panel.iloc[:, 1:].pct_change().dropna().iloc[-self._lag_order:]
        forecast = self.var_results.forecast(last_obs.values, steps=steps)
        names = panel.columns[1:]
        forecast_df = pd.DataFrame(
            forecast, columns=names,
            index=pd.RangeIndex(start=1, stop=steps + 1, name="step")
        )
        return forecast_df

    def get_causal_network(self, panel: pd.DataFrame, top_k: int = 10) -> List[Dict]:
        matrix = self.granger_causality(panel)
        pairs = []
        names = matrix.columns
        for i in range(len(names)):
            for j in range(len(names)):
                if i != j and matrix.iloc[i, j] > -np.log10(self.granger_alpha):
                    pairs.append({
                        "cause": names[j],
                        "effect": names[i],
                        "strength": float(matrix.iloc[i, j]),
                    })
        pairs.sort(key=lambda x: x["strength"], reverse=True)
        return pairs[:top_k]
