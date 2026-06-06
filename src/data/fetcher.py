# -*- coding: utf-8 -*-
"""
Data fetcher module - Tencent QQ Finance API
"""
import json
import time
import pathlib
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import requests

from config import DATA_CONFIG


class DataFetcher:
    """A-share sector ETF data fetcher from Tencent QQ Finance API"""

    BASE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self, config=None):
        self.config = config or DATA_CONFIG
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self._cache_dir = pathlib.Path(self.config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _parse_secid(self, symbol: str) -> str:
        code = symbol.split(".")[0]
        suffix = symbol.split(".")[1].upper()
        market = "sh" if suffix == "SH" else "sz"
        return f"{market}{code}"

    def fetch_etf_daily(self, symbol: str, days: Optional[int] = None) -> pd.DataFrame:
        days = days or self.config.history_days
        secid = self._parse_secid(symbol)
        params = {"param": f"{secid},day,,,{days},qfq"}
        try:
            resp = self._session.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [WARN] {symbol} fetch failed: {e}")
            return pd.DataFrame()

        if data.get("code") != 0:
            return pd.DataFrame()

        # Try qfqday (forward-adjusted daily) first, fall back to day
        try:
            klines = data["data"][secid].get("qfqday") or data["data"][secid].get("day")
            if not klines:
                return pd.DataFrame()
        except (KeyError, TypeError):
            try:
                klines = (
                    list(data["data"].values())[0].get("qfqday")
                    or list(data["data"].values())[0].get("day")
                    or []
                )
            except (KeyError, IndexError, AttributeError):
                return pd.DataFrame()

        if not klines:
            return pd.DataFrame()

        rows = []
        for parts in klines:
            if len(parts) < 5:
                continue
            try:
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]) if len(parts) > 5 else 0,
                    "symbol": symbol,
                })
            except (ValueError, IndexError):
                continue

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df

    def fetch_all_sectors(self, days: Optional[int] = None) -> Dict[str, pd.DataFrame]:
        days = days or self.config.history_days
        result = {}
        for name, symbol in self.config.sector_etfs.items():
            print(f"  Downloading {name} ({symbol})...")
            df = self.fetch_etf_daily(symbol, days)
            if not df.empty:
                result[name] = df
                print(f"    -> {len(df)} rows")
            else:
                print(f"    -> No data")
            time.sleep(0.2)
        return result

    def build_price_panel(self, days: Optional[int] = None) -> pd.DataFrame:
        etf_data = self.fetch_all_sectors(days)
        if not etf_data:
            return pd.DataFrame()

        panel = pd.DataFrame()
        for name, df in etf_data.items():
            series = df[["date", "close"]].copy()
            series = series.rename(columns={"close": name})
            if panel.empty:
                panel = series
            else:
                panel = panel.merge(series, on="date", how="outer")
        panel = panel.sort_values("date").reset_index(drop=True)
        panel = panel.ffill().bfill()

        if len(panel) < 60:
            print(f"  [WARN] Only {len(panel)} trading days fetched")
        else:
            print(f"\n  Total: {len(panel)} trading days, {len(panel.columns)-1} sectors")
            print(f"  Date range: {panel['date'].iloc[0].date()} ~ {panel['date'].iloc[-1].date()}")

        return panel
