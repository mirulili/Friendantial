import re
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict

import pandas as pd
import FinanceDataReader as fdr
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
    for code in codes:
        base = re.sub(r"\.[A-Z]{2}$", "", code)
        try:
            df = fdr.DataReader(base, start=start_dt.isoformat(), end=end_dt.isoformat())
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
            logging.warning("Data load failed for %s (%s): %s", code, base, e)
            out[code] = pd.DataFrame()
    return out