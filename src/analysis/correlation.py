# -*- coding: utf-8 -*-
"""
Sector correlation analysis module
"""
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, coint


class CorrelationAnalyzer:
    """Analyze correlation and cointegration between sectors"""

    @staticmethod
    def pearson_correlation(panel: pd.DataFrame) -> pd.DataFrame:
        """Pearson correlation matrix based on returns"""
        returns = panel.iloc[:, 1:].pct_change().dropna()
        return returns.corr()

    @staticmethod
    def rolling_correlation(panel: pd.DataFrame, window: int = 60) -> pd.DataFrame:
        """Rolling correlation to observe relationship changes over time"""
        returns = panel.iloc[:, 1:].pct_change().dropna()
        rolling_corr = returns.rolling(window=window).corr()
        return rolling_corr

    @staticmethod
    def check_stationarity(series: pd.Series, alpha: float = 0.05) -> dict:
        """ADF stationarity test"""
        stat, pval, usedlag, nobs, crit_values, icbest = adfuller(
            series.dropna(), autolag="AIC"
        )
        return {
            "statistic": stat,
            "pvalue": pval,
            "is_stationary": pval < alpha,
            "critical_values": crit_values,
        }

    @staticmethod
    def cointegration_test(y1: pd.Series, y2: pd.Series, alpha: float = 0.05) -> dict:
        """Engle-Granger cointegration test"""
        score, pval, _ = coint(y1.dropna(), y2.dropna(), autolag="AIC")
        return {
            "score": score,
            "pvalue": pval,
            "is_cointegrated": pval < alpha,
        }

    def find_cointegrated_pairs(self, panel: pd.DataFrame) -> list:
        """Find all cointegrated sector pairs"""
        names = [c for c in panel.columns if c != "date"]
        results = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                test = self.cointegration_test(panel[names[i]], panel[names[j]])
                if test["is_cointegrated"]:
                    results.append({
                        "pair": (names[i], names[j]),
                        "score": test["score"],
                        "pvalue": test["pvalue"],
                    })
        return sorted(results, key=lambda x: x["pvalue"])

    @staticmethod
    def build_distance_matrix(panel: pd.DataFrame) -> pd.DataFrame:
        """Distance matrix from returns (for clustering)"""
        returns = panel.iloc[:, 1:].pct_change().dropna()
        corr = returns.corr()
        dist = np.sqrt(2 * (1 - corr))
        return pd.DataFrame(dist, index=corr.index, columns=corr.columns)
