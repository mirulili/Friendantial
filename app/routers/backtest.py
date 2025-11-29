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


@router.get("/simulate", summary="백테스트")
async def backtest_strategy(
    target_date: str = Query(..., description="백테스트 기준일 (YYYY-MM-DD)"),
    strategy: StrategyEnum = Query(StrategyEnum.DAY_TRADER, description="전략 선택"),
    codes: Optional[str] = Query(None, description="종목 코드 (예: 005930.KS)"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    # 백테스트 수익률 계산에 필요한 의존성만 남김
    client: httpx.AsyncClient = Depends(get_http_client),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    """
    특정 날짜와 전략을 기준으로 과거 시점의 종목 추천을 시뮬레이션하고, 이후 수익률을 분석합니다.
    1. 특정 종목을 시뮬레이션 하는 경우: codes를 입력해 주세요. 전략은 선택하지 마세요.
    2. 전체 유니버스를 시뮬레이션 하는 경우: codes를 입력하지 마세요. 원하는 전략을 선택해 주세요.
    """
    # 1. 분석 대상 종목 설정
    if codes:
        universe_codes = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        universe_codes = None  # 특정 코드가 없으면 전체 유니버스 사용

    logging.info(f"Backtesting on {target_date} for {universe_codes or 'ALL'}")

    # 2. 중앙 분석 워크플로우 실행
    reco_response = await analysis_service.run_backtest_recommendations(
        strategy=strategy, as_of=target_date, universe_codes=universe_codes
    )

    recommended_stocks = reco_response.candidates
    if not recommended_stocks:
        return {"message": "해당 날짜에 추천된 종목이 없습니다.", "backtest_result": []}

    results = []

    # 3. 추천일로부터 7일 후의 수익률 확인
    future_date = (
        datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=7)
    ).strftime("%Y-%m-%d")

    # 모든 추천 종목의 미래 데이터를 한 번에 조회
    # 참고: lookback_days=10은 미래 시점(future_date) 기준 과거 10일치 데이터를 가져온다는 의미입니다.
    # 참고: 만약 future_date 당일 데이터가 없다면(휴장일 등), 해당 기간 내 가장 최신 데이터를 사용하게 됩니다.
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
