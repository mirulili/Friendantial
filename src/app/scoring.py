from typing import Optional, Dict
import pandas as pd
from .models import FeatureConf, StockScore

def compute_features(df: pd.DataFrame, conf: FeatureConf) -> pd.DataFrame:
    df = df.copy()
    df["ret1"] = df["close"].pct_change(fill_method=None)
    for win in [conf.mom_short, conf.mom_med, conf.mom_long]:
        df[f"mom{win}"] = df["close"].pct_change(win, fill_method=None)
    return df

def score_stock(
    code: str, 
    name: str, 
    df: pd.DataFrame, 
    mom_z_scores: Dict[str, float],
    news_score: float, 
    volatility_score: float, 
    conf: FeatureConf, 
    market_regime: str = "NEUTRAL"
) -> Optional[StockScore]:
    if len(df) < conf.mom_long + 2:
        return None
    prev = df.iloc[-2]

    # 시장 상황에 따라 최소 거래대금 기준을 동적으로 조정
    min_turnover = conf.min_turnover_won * 1.5 if market_regime == "BEAR" else conf.min_turnover_won
    if prev.get("value_traded", 0.0) < min_turnover:
        return None

    # 시장 상황에 따라 모멘텀 가중치 동적 조정
    if market_regime == "BULL":
        mom_weights = (0.6, 0.3, 0.1) # 상승장: 단기 모멘텀 강화
    elif market_regime == "BEAR":
        mom_weights = (0.4, 0.3, 0.3) # 하락장: 장기 추세 비중 강화
    else: # NEUTRAL
        mom_weights = (0.55, 0.3, 0.15)

    # Z-Score를 가중 합산하여 최종 모멘텀 점수 계산
    z5 = mom_z_scores.get(f"mom{conf.mom_short}", 0.0)
    z20 = mom_z_scores.get(f"mom{conf.mom_med}", 0.0)
    z60 = mom_z_scores.get(f"mom{conf.mom_long}", 0.0)
    mom_core = mom_weights[0] * z5 + mom_weights[1] * z20 + mom_weights[2] * z60

    # 변동성 패널티와 뉴스 가중치도 시장 상황에 따라 조정
    # news_score는 이제 0~1 사이의 정규화된 값이므로, 가중치를 조정하여 영향력을 조절할 수 있습니다.
    # volatility_score도 0~1 사이의 정규화된 값입니다.
    vol_penalty_weight = 0.7 if market_regime == "BEAR" else 0.5
    news_impact_factor = 0.1 # 뉴스 점수의 최대 영향력을 0.1로 설정

    score = mom_core - vol_penalty_weight * volatility_score + news_impact_factor * float(news_score or 0.0)

    reason = f"mom={mom_core:.3f}, vol_penalty={volatility_score:.3f}, news={float(news_score or 0.0):.3f}"
    
    # reason에 표시할 원본 모멘텀 값
    m5 = float(prev[f"mom{conf.mom_short}"])
    m20 = float(prev[f"mom{conf.mom_med}"])
    m60 = float(prev[f"mom{conf.mom_long}"])
    return StockScore(
        code=code, name=name, score=float(score), reason=reason,
        momentum={"m5": m5, "m20": m20, "m60": m60},
        news_sentiment_score=float(news_score) if news_score is not None else None,
    )