import logging

from fastapi import Request

from ..config import MARKET
from ..services.market_data import fetch_ohlcv


import httpx

# ...

async def determine_market_regime(
    client: httpx.AsyncClient, request: Request, as_of: str
) -> str:
    """시장 대표 ETF를 분석하여 현재 시장 상황(BULL/BEAR/NEUTRAL)을 판단합니다."""
    market_regime = "NEUTRAL"
    # KOSPI: KODEX 200, KOSDAQ: KODEX KOSDAQ 150
    market_index_ticker = "069500.KS" if MARKET.upper() == "KS" else "229200.KS"

    try:
        market_index_data = await fetch_ohlcv(
            client, request, [market_index_ticker], end_date=as_of, lookback_days=30
        )
        df_index = market_index_data.get(market_index_ticker)

        if df_index is not None and not df_index.empty and len(df_index) >= 20:
            last_close = df_index["close"].iloc[-1]
            ma20 = df_index["close"].rolling(window=20).mean().iloc[-1]

            if last_close > ma20:
                market_regime = "BULL"
            else:
                market_regime = "BEAR"

            logging.info(
                f"시장 상황 판단: {market_regime} (종가: {last_close:.2f}, MA20: {ma20:.2f})"
            )
    except Exception as e:
        logging.warning(f"시장 상황 판단 실패: {e}. 'NEUTRAL'로 진행합니다.")

    return market_regime
