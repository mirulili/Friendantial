# app/core/scoring.py

from typing import Dict, Optional, Tuple

import pandas as pd

from ..schemas.models import FeatureConf, StockScore
from .strategies import get_strategy


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI(Relative Strength Index)를 계산합니다. (Wilder's Smoothing 적용)"""
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Wilder's Smoothing (alpha = 1/period)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR(Average True Range)을 계산합니다. (Wilder's Smoothing 적용)"""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's Smoothing
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def calculate_z_scores(
    features: pd.Series, mom_stats: Dict[str, Tuple[float, float]]
) -> Dict[str, float]:
    """
    모멘텀 통계(평균, 표준편차)를 사용하여 Z-Score를 계산합니다.

    Args:
        features (pd.Series): 종목의 피쳐 데이터 (mom5, mom20, mom60 등 포함)
        mom_stats (Dict[str, Tuple[float, float]]): 모멘텀별 (평균, 표준편차) 통계

    Returns:
        Dict[str, float]: 계산된 Z-Score 딕셔너리
    """
    z_scores = {}
    for key, (mean, std) in mom_stats.items():
        z_scores[key] = (float(features.get(key, 0.0)) - mean) / std if std > 0 else 0.0
    return z_scores


def compute_features(df: pd.DataFrame, conf: FeatureConf) -> pd.DataFrame:
    """
    주가 데이터(OHLCV)를 기반으로 기술적 지표(이동평균, 모멘텀, RSI, ATR 등)를 계산합니다.

    Args:
        df (pd.DataFrame): OHLCV 데이터프레임
        conf (FeatureConf): 피쳐 설정 객체

    Returns:
        pd.DataFrame: 기술적 지표가 추가된 데이터프레임
    """
    df = df.copy()

    # 1. 수익률 및 이동평균선
    df["ret1"] = df["close"].pct_change(fill_method=None)
    df["ma5"] = df["close"].rolling(window=5).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma60"] = df["close"].rolling(window=60).mean()  # 장기 추세용

    # 2. 거래량 이동평균
    df["avg_vol20"] = df["volume"].rolling(window=20).mean()

    # 3. 모멘텀
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
    """
    주어진 종목의 데이터를 분석하여 점수를 계산합니다.
    전략(Strategy) 패턴을 사용하여 전략별로 다른 로직을 적용합니다.

    Args:
        code (str): 종목 코드
        name (str): 종목명
        df (pd.DataFrame): OHLCV 및 피쳐 데이터프레임
        mom_z_scores (Dict[str, float]): 모멘텀 Z-Score
        news_score (float): 뉴스 감성 점수
        volatility_score (float): 변동성 점수
        conf (FeatureConf): 피쳐 설정 객체
        market_regime (str): 시장 상황 (BULL, BEAR, NEUTRAL)
        strategy (str): 적용할 전략 이름

    Returns:
        Optional[StockScore]: 계산된 종목 점수 객체 (조건 불만족 시 None)
    """

    if len(df) < conf.mom_long + 2:
        return None

    prev = df.iloc[-2]  # 직전 거래일 기준

    # --- 기본 데이터 추출 ---
    last_close = prev.get("close", 0.0)
    rsi = prev.get("rsi", 50.0)
    atr_ratio = prev.get("atr_ratio", 0.0)  # ATR / Close 비율

    # 거래대금 필터링
    min_turnover = (
        conf.min_turnover_won * 1.5
        if market_regime == "BEAR"
        else conf.min_turnover_won
    )
    if prev.get("value_traded", 0.0) < min_turnover:
        return None

    # --- 전략 적용 ---
    strategy_impl = get_strategy(strategy)

    # 1. RSI 보너스 계산
    rsi_bonus = strategy_impl.calculate_rsi_bonus(rsi)

    # 2. MA 페널티 및 경고 확인
    ma_penalty, warnings = strategy_impl.check_ma_penalty(last_close, prev)

    gap_bonus = 0.0

    # --- 점수 계산 ---
    mom_weights = strategy_impl.mom_weights
    vol_penalty_weight = strategy_impl.vol_penalty_weight
    news_impact_factor = strategy_impl.news_impact_factor

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
        reason_parts.append("RSI보너스")
    if ma_penalty > 0:
        reason_parts.append("MA이탈")

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
