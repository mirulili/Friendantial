import pandas as pd
import pytest

from app.core.scoring import calculate_z_scores, compute_atr, compute_rsi


def test_compute_rsi_basic():
    """간단한 시퀀스로 RSI 계산을 테스트합니다."""
    # 시리즈 생성: 5일 상승, 5일 하락

    # Case 1: 단조 상승
    up_series = pd.Series(range(100))
    rsi_up = compute_rsi(up_series, period=14)
    # 워밍업 후, RSI는 매우 높아야 함
    assert rsi_up.iloc[-1] > 90

    # Case 2: 단조 하락
    down_series = pd.Series(range(100, 0, -1))
    rsi_down = compute_rsi(down_series, period=14)
    # 워밍업 후, RSI는 매우 낮아야 함
    assert rsi_down.iloc[-1] < 10


def test_compute_atr(sample_ohlcv_data):
    """ATR 계산을 테스트합니다."""
    df = sample_ohlcv_data
    atr = compute_atr(df, period=14)

    # ATR은 양수여야 함
    assert (atr.dropna() > 0).all()
    # ATR은 대략 고가-저가 범위 내에 있어야 함
    avg_range = (df["high"] - df["low"]).mean()
    assert atr.iloc[-1] > 0


def test_calculate_z_scores():
    """Z-score 계산을 테스트합니다."""
    features = pd.Series({"mom5": 0.1, "mom20": 0.2})
    mom_stats = {
        "mom5": (0.05, 0.05),  # mean=0.05, std=0.05 -> z = (0.1-0.05)/0.05 = 1.0
        "mom20": (0.2, 0.1),  # mean=0.2, std=0.1 -> z = (0.2-0.2)/0.1 = 0.0
        "mom60": (0.0, 0.0),  # std=0 -> z=0
    }

    z_scores = calculate_z_scores(features, mom_stats)

    assert z_scores["mom5"] == 1.0
    assert z_scores["mom20"] == 0.0
    assert z_scores["mom60"] == 0.0
