from typing import Optional, Dict
import pandas as pd
from .models import FeatureConf, StockScore

def compute_features(df: pd.DataFrame, conf: FeatureConf) -> pd.DataFrame:
    df = df.copy()
    df["ret1"] = df["close"].pct_change(fill_method=None)
    # 이동평균선(MA) 계산
    df["ma5"] = df["close"].rolling(window=5).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["avg_vol20"] = df["volume"].rolling(window=20).mean() # 거래량 급등 비교를 위한 20일 평균 거래량
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
    market_regime: str = "NEUTRAL",
    strategy: str = "default" # 트레이딩 전략 파라미터 추가
) -> Optional[StockScore]:
    if len(df) < conf.mom_long + 2:
        return None
    prev = df.iloc[-2]
    
    # --- 데이 트레이딩 전략 추가 ---
    warnings = []
    ma_penalty = 0.0
    gap_bonus = 0.0
    last_close = prev.get("close", 0.0)

    # 시장 상황에 따라 최소 거래대금 기준을 동적으로 조정
    min_turnover = conf.min_turnover_won * 1.5 if market_regime == "BEAR" else conf.min_turnover_won
    if prev.get("value_traded", 0.0) < min_turnover:
        return None

    # =================================================================
    # --- 전략(strategy)별 로직 분기 ---
    # =================================================================

    if strategy == "day_trader":
        # --- 1-1. 단기 트레이더 전략 ---
        mom_weights = (0.7, 0.3, 0.0) 
        vol_penalty_weight = 0.3 # 변동성은 기회일 수 있으므로 페널티 약화
        news_impact_factor = 0.3 # 단기 뉴스의 영향력 강화

        # 이동평균선 페널티 (단기 추세 이탈에 민감)
        if last_close < prev.get("ma5", float('inf')):
            ma_penalty = 0.6 # 5일선 이탈 시 강한 페널티
            warnings.append("5일선 이탈")
        elif last_close < prev.get("ma20", float('inf')):
            ma_penalty = 0.3 # 20일선 이탈 시 약한 페널티
            warnings.append("20일선 이탈")

        # 전일 등락률 가중치 (갭 상승/하락에 민감)
        prev_return = prev.get("ret1", 0.0)
        if prev_return > 0.03:
            gap_bonus = 0.2
        elif prev_return < -0.03:
            gap_bonus = -0.2

        # 거래량 급등 경고
        last_volume = prev.get("volume", 0.0)
        avg_volume = prev.get("avg_vol20", 0.0)
        if avg_volume > 0 and last_volume > avg_volume * 3:
            warnings.append("거래량 급등")

    elif strategy == "long_term":
        # --- 1-2. 장기 투자자 전략 ---
        mom_weights = (0.2, 0.4, 0.4)
        vol_penalty_weight = 0.8 # 안정성을 중시하므로 변동성 페널티 강화
        news_impact_factor = 0.15 # 단기 뉴스 영향력 약화
        gap_bonus = 0.0 # 갭 상승/하락은 장기 추세에 무의미하므로 무시

        # 이동평균선 페널티 (장기 추세에 집중)
        if last_close < prev.get("ma60", float('inf')):
            ma_penalty = 0.4 # 60일선(장기 추세선) 이탈 시 페널티
            warnings.append("장기 추세 이탈")

    else: # --- 1-3. 기본(default) 전략: 기존 로직 유지 ---
        if market_regime == "BULL":
            mom_weights = (0.6, 0.3, 0.1) # 상승장: 단기 모멘텀 강화
        elif market_regime == "BEAR":
            mom_weights = (0.4, 0.3, 0.3) # 하락장: 장기 추세 비중 강화
        else: # NEUTRAL
            mom_weights = (0.55, 0.3, 0.15)
        
        vol_penalty_weight = 0.7 if market_regime == "BEAR" else 0.5
        news_impact_factor = 0.2
        
        if last_close < prev.get("ma5", float('inf')) or last_close < prev.get("ma20", float('inf')):
            ma_penalty = 0.5
            warnings.append("MA 이탈")

    # =================================================================
    # --- 2. 공통 점수 계산 ---
    # =================================================================
    z5 = mom_z_scores.get(f"mom{conf.mom_short}", 0.0)
    z20 = mom_z_scores.get(f"mom{conf.mom_med}", 0.0)
    z60 = mom_z_scores.get(f"mom{conf.mom_long}", 0.0)
    mom_core = mom_weights[0] * z5 + mom_weights[1] * z20 + mom_weights[2] * z60
    mom_core += 1e-6

    # 최종 점수 계산
    score = mom_core - vol_penalty_weight * volatility_score + news_impact_factor * float(news_score or 0.0) - ma_penalty + gap_bonus
    
    reason = f"mom={mom_core:.3f}, vol_p={volatility_score:.3f}, news={float(news_score or 0.0):.3f}, ma_p={ma_penalty:.1f}, gap={gap_bonus:.1f}"
    if warnings:
        reason += f" [주의: {', '.join(warnings)}]"

    # reason에 표시할 원본 모멘텀 값
    m5 = float(prev[f"mom{conf.mom_short}"])
    m20 = float(prev[f"mom{conf.mom_med}"])
    m60 = float(prev[f"mom{conf.mom_long}"])
    return StockScore(
        code=code, name=name, score=float(score), reason=reason,
        momentum={"m5": m5, "m20": m20, "m60": m60},
        news_sentiment_score=float(news_score) if news_score is not None else None,
    )