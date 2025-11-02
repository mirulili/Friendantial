from typing import Optional
import pandas as pd
from .models import FeatureConf, StockScore

def compute_features(df: pd.DataFrame, conf: FeatureConf) -> pd.DataFrame:
    df = df.copy()
    df["ret1"] = df["close"].pct_change(fill_method=None)
    for win in [conf.mom_short, conf.mom_med, conf.mom_long]:
        df[f"mom{win}"] = df["close"].pct_change(win, fill_method=None)
    return df

def score_stock(code: str, name: str, df: pd.DataFrame, news_score: float, conf: FeatureConf) -> Optional[StockScore]:
    if len(df) < conf.mom_long + 2:
        return None
    prev = df.iloc[-2]

    if prev.get("value_traded", 0.0) < conf.min_turnover_won:
        return None

    m5 = float(prev[f"mom{conf.mom_short}"])
    m20 = float(prev[f"mom{conf.mom_med}"])
    m60 = float(prev[f"mom{conf.mom_long}"])

    mom_core = 0.55 * m5 + 0.30 * m20 + 0.15 * m60
    vol_penalty = float(df["ret1"].rolling(20).std().iloc[-2])
    score = mom_core - 0.5 * vol_penalty + 0.1 * float(news_score or 0.0)

    reason = f"mom={mom_core:.3f}, vol_penalty={vol_penalty:.3f}, news={float(news_score or 0.0):.3f}"
    return StockScore(
        code=code, name=name, score=float(score), reason=reason,
        momentum={"m5": m5, "m20": m20, "m60": m60},
        news_sentiment_score=float(news_score) if news_score is not None else None,
    )