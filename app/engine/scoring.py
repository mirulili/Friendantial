# app/scoring.py

from typing import Dict, Optional

import pandas as pd

from ..schemas.models import FeatureConf, StockScore


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI(Relative Strength Index)를 계산합니다."""
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR(Average True Range)을 계산합니다."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_features(df: pd.DataFrame, conf: FeatureConf) -> pd.DataFrame:
    df = df.copy()

    # 1. 수익률 및 이동평균선
    df["ret1"] = df["close"].pct_change(fill_method=None)
    df["ma5"] = df["close"].rolling(window=5).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma60"] = df["close"].rolling(window=60).mean()  # 장기 추세용 추가

    # 2. 거래량 이동평균
    df["avg_vol20"] = df["volume"].rolling(window=20).mean()

    # 3. 모멘텀 (기존 로직)
    for win in [conf.mom_short, conf.mom_med, conf.mom_long]:
        df[f"mom{win}"] = df["close"].pct_change(win, fill_method=None)

    # 4. 기술적 지표 (RSI, ATR)
    # 데이터가 충분한지 확인 후 계산 (최소 14일 + 여유분)
    if len(df) > 20:
        df["rsi"] = compute_rsi(df["close"], period=14)
        df["atr"] = compute_atr(df, period=14)

        # ATR을 주가 대비 비율로 정규화 (ATR%): 가격이 다른 종목끼리 비교하기 위함
        df["atr_ratio"] = df["atr"] / df["close"]
    else:
        # 데이터 부족 시 기본값 처리
        df["rsi"] = 50.0
        df["atr_ratio"] = 0.0

    return df


def score_stock(
    code: str,
    name: str,
    df: pd.DataFrame,
    mom_z_scores: Dict[str, float],
    news_score: float,
    volatility_score: float,  # 외부에서 ret1 std로 계산된 값 (Z-score)
    conf: FeatureConf,
    market_regime: str = "NEUTRAL",
    strategy: str = "default",
) -> Optional[StockScore]:

    if len(df) < conf.mom_long + 2:
        return None

    prev = df.iloc[-2]  # 직전 거래일 기준

    # --- 기본 데이터 추출 ---
    last_close = prev.get("close", 0.0)
    rsi = prev.get("rsi", 50.0)
    atr_ratio = prev.get("atr_ratio", 0.0)  # ATR / Close 비율

    warnings = []
    ma_penalty = 0.0
    gap_bonus = 0.0
    rsi_bonus = 0.0  # RSI 보너스 추가

    # 거래대금 필터링
    min_turnover = (
        conf.min_turnover_won * 1.5
        if market_regime == "BEAR"
        else conf.min_turnover_won
    )
    if prev.get("value_traded", 0.0) < min_turnover:
        return None

    # --- 전략(strategy)별 로직 분기 ---

    if strategy == "day_trader":
        # [단타] 과매도 반등 + 단기 모멘텀
        mom_weights = (0.5, 0.2, 0.0)  # 단기 비중 높임, 장기 무시
        vol_penalty_weight = 0.2  # 변동성 용인 (기회로 봄)
        news_impact_factor = 0.4  # 뉴스 민감도 높임

        # --- RSI 과매도 구간 반등 전략 ---
        if rsi < 30:
            rsi_bonus = 2.0  # 과매도 구간: 강력한 매수 신호
        elif rsi > 70:
            rsi_bonus = -1.0  # 과매수 구간: 주의

        # 단기 이평선 이탈 체크
        if last_close < prev.get("ma5", float("inf")):
            ma_penalty = 0.5
            warnings.append("5일선 이탈")

    elif strategy == "long_term":
        # [장투] 추세 추종 + 안정성
        mom_weights = (0.1, 0.3, 0.6)  # 장기 비중 압도적
        vol_penalty_weight = 1.5  # 변동성 극도로 싫어함 (ATR 페널티 강화)
        news_impact_factor = 0.1

        # RSI는 장기 투자에서 중간값(40~60)일 때 안정적
        if rsi < 30 or rsi > 70:
            rsi_bonus = -0.5  # 극단적인 지표는 장기 투자에 불안 요소임을 반영

        if last_close < prev.get("ma60", float("inf")):
            ma_penalty = 1.0
            warnings.append("장기 추세 훼손")

    else:  # Default
        mom_weights = (0.4, 0.3, 0.3)
        vol_penalty_weight = 0.5
        news_impact_factor = 0.2

        # 일반적인 RSI 필터
        if rsi < 30:
            rsi_bonus = 0.5  # 저점 매수 기회
        elif rsi > 80:
            rsi_bonus = -0.5  # 과열

    # --- 점수 계산 ---

    # 1. 모멘텀 점수 (Z-Score 기반)
    z5 = mom_z_scores.get(f"mom{conf.mom_short}", 0.0)
    z20 = mom_z_scores.get(f"mom{conf.mom_med}", 0.0)
    z60 = mom_z_scores.get(f"mom{conf.mom_long}", 0.0)
    mom_core = mom_weights[0] * z5 + mom_weights[1] * z20 + mom_weights[2] * z60

    # 2. 변동성 페널티 (ATR 반영)
    # ATR 비율이 높으면(예: 3% 이상) 페널티 부여
    atr_penalty = max(0, (atr_ratio - 0.03) * 10)

    final_vol_penalty = (vol_penalty_weight * volatility_score) + (atr_penalty * 0.5)

    # 3. 최종 산식
    score = (
        mom_core
        - final_vol_penalty
        + (news_impact_factor * float(news_score or 0.0))
        - ma_penalty
        + gap_bonus
        + rsi_bonus
    )

    # 디버깅/설명용 Reason 생성
    reason_parts = [
        f"mom={mom_core:.2f}",
        f"vol_p={final_vol_penalty:.2f}",
        f"rsi={rsi:.0f}",
    ]
    if rsi_bonus > 0:
        reason_parts.append(f"RSI보너스")
    if ma_penalty > 0:
        reason_parts.append(f"MA이탈")

    reason = ", ".join(reason_parts)
    if warnings:
        reason += f" [주의: {', '.join(warnings)}]"

    return StockScore(
        code=code,
        name=name,
        score=round(float(score), 2),
        reason=reason,
        momentum={
            "m5": round(float(prev.get(f"mom{conf.mom_short}", 0)), 4),
            "m20": round(float(prev.get(f"mom{conf.mom_med}", 0)), 4),
            "m60": round(float(prev.get(f"mom{conf.mom_long}", 0)), 4),
            "rsi": round(float(prev.get("rsi", 50.0)), 2),
        },
        news_sentiment_score=(
            round(float(news_score), 3) if news_score is not None else None
        ),
        price=float(last_close),  # 종가 정보
    )
