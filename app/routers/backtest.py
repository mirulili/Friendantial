# app/routers/backtest.py

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_http_client, get_redis_connection
from app.routers.basic_analysis import get_analysis_service
from app.schemas.enums import StrategyEnum
from app.services.analysis import AnalysisService
from app.services.market_data import fetch_ohlcv

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/simulate")
async def backtest_strategy(
    target_date: str = Query(..., description="백테스트 기준일 (YYYY-MM-DD)"),
    strategy: StrategyEnum = Query(StrategyEnum.DAY_TRADER, description="전략 선택"),
    codes: Optional[str] = Query(None, description="종목 코드 (예: 005930.KS)"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    # 백테스트 수익률 계산에 필요한 의존성만 남김
    client: httpx.AsyncClient = Depends(get_http_client),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    # 1. 분석 대상 종목을 설정합니다. (입력이 없으면 전체 유니버스 사용)
    if codes:
        universe_codes = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        universe_codes = (
            None  # None으로 전달하여 서비스가 전체 유니버스를 사용하도록 합니다.
        )

    logging.info(f"Backtesting on {target_date} for {universe_codes or 'ALL'}")

    # 2. 중앙 분석 워크플로우 실행
    reco_response = await analysis_service.run_backtest_recommendations(
        strategy=strategy, as_of=target_date, universe_codes=universe_codes
    )

    recommended_stocks = reco_response.candidates
    if not recommended_stocks:
        return {"message": "해당 날짜에 추천된 종목이 없습니다.", "backtest_result": []}

    results = []
    # 3. 추천일로부터 7일 후의 수익률을 확인합니다.
    future_date = (
        datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=7)
    ).strftime("%Y-%m-%d")

    # 모든 추천 종목의 미래 데이터를 한 번에 조회
    future_data_map = await fetch_ohlcv(
        client,
        redis_conn,
        [s.code for s in recommended_stocks],
        end_date=future_date,
        lookback_days=10,
    )

    for reco_item in recommended_stocks:
        buy_price = reco_item.price
        future_df = future_data_map.get(reco_item.code)

        if future_df is None or future_df.empty:
            profit = "N/A"
            result_msg = "미래 데이터 없음"
        else:
            try:
                sell_price = future_df["close"].iloc[-1]
                profit_pct = (
                    (sell_price - buy_price) / buy_price if buy_price > 0 else 0
                )
                profit = f"{profit_pct:.2%}"
                result_msg = "성공(수익)" if profit_pct > 0 else "실패(손실)"
            except (IndexError, ZeroDivisionError):
                profit = "N/A"
                result_msg = "수익률 계산 실패"

        results.append(
            {
                "code": reco_item.code,
                "name": reco_item.name,
                "date": target_date,
                "score": round(reco_item.score, 2),
                "decision": "매수 추천",
                "return": profit,
                "result_msg": result_msg,
            }
        )

    return {"backtest_result": results}
