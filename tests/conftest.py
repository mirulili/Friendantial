import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_data():
    """테스트를 위한 샘플 OHLCV 데이터프레임을 생성합니다."""
    dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
    data = {
        "open": np.random.uniform(100, 200, 100),
        "high": np.random.uniform(100, 200, 100),
        "low": np.random.uniform(100, 200, 100),
        "close": np.random.uniform(100, 200, 100),
        "volume": np.random.randint(1000, 10000, 100),
    }
    df = pd.DataFrame(data, index=dates)
    # 고가가 가장 높고 저가가 가장 낮은지 확인
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df
