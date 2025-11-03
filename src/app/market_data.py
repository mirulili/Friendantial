import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict

import pandas as pd
import yfinance as yf
from fastapi import HTTPException

from .config import TZ

def fetch_ohlcv(codes: List[str], end_date: Optional[str] = None, lookback_days: int = 120) -> Dict[str, pd.DataFrame]:
    if end_date is None:
        end_date = datetime.now(TZ).date().isoformat()
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid as_of date '{end_date}'; expected YYYY-MM-DD")
    start_dt = end_dt - timedelta(days=max(lookback_days, 30))
    
    out: Dict[str, pd.DataFrame] = {}
    try:
        # yfinance can download multiple tickers at once
        df_multi = yf.download(codes, start=start_dt, end=end_dt, progress=False)
        for code in codes:
            df = df_multi.xs(code, level=1, axis=1) if len(codes) > 1 else df_multi
            if df is None or df.empty:
                out[code] = pd.DataFrame()
                continue
            
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            df = df[keep].copy()
            df.index.name = "date"
            df = df.sort_index()
            df["value_traded"] = df["close"] * df["volume"]
            out[code] = df
    except Exception as e:
        logging.error("yfinance data download failed: %s", e)
        for code in codes:
            out[code] = pd.DataFrame() # Return empty dataframe for all on failure
    return out