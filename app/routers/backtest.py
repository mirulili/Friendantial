import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_http_client
import httpx

from app.engine.scoring import compute_features, score_stock
from app.schemas.models import FeatureConf
from app.services.market_data import fetch_ohlcv

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/simulate")
async def backtest_strategy(
    request: Request,
    target_date: str,
    strategy: str = "day_trader",
    codes: Optional[str] = Query(None, description="종목 코드 (예: 005930.KS)"),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    # 1. 종목 설정
    if codes:
        sample_codes = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        sample_codes = ["005930.KS", "000660.KS", "005380.KS", "035420.KS", "005935.KS"]

    logging.info(f"Backtesting on {target_date} for {sample_codes}")

    # 2. 데이터 조회 (과거 시점)
    data = await fetch_ohlcv(
        client, request, sample_codes, end_date=target_date, lookback_days=120
    )

    results = []
    conf = FeatureConf()

    for code, df in data.items():
        if df.empty or len(df) < 30:
            continue

        # 3. 지표 계산
        features = compute_features(df, conf)

        # --- Self-Z-Score 계산 ---
        # 시장 전체 데이터가 없으므로, 해당 종목의 과거(120일) 데이터와 비교하여 Z-Score 산출
        z_scores = {}
        for win in [conf.mom_short, conf.mom_med, conf.mom_long]:
            col = f"mom{win}"
            if col in features.columns:
                # 최근 120일치 모멘텀의 평균과 표준편차 계산
                series = features[col].dropna()
                if not series.empty:
                    mean = series.mean()
                    std = series.std()
                    current_val = series.iloc[
                        -2
                    ]  # 어제 종가 기준 (오늘 시초가 매수 가정)

                    # 표준편차가 0이 아니면 Z-Score 계산
                    if std > 0:
                        z_scores[col] = (current_val - mean) / std
                    else:
                        z_scores[col] = 0.0

        # 4. 점수 산출
        score_obj = score_stock(
            code,
            code,
            features,
            z_scores,
            0,
            0,
            conf,
            strategy=strategy,
        )

        if score_obj:
            # 5. 전략 판단 (기준 점수)
            # Self-Z-Score는 변동폭이 크므로 기준을 0점으로 설정
            buy_threshold = 0.0
            decision = "매수" if score_obj.score > buy_threshold else "관망(매수X)"

            # 6. 미래 수익률 확인 (7일 뒤)
            future_date = (
                datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=7)
            ).strftime("%Y-%m-%d")
            future_data = await fetch_ohlcv(
                client, request, [code], end_date=future_date, lookback_days=10
            )

            if not future_data[code].empty:
                try:
                    buy_price = features["close"].iloc[-1]
                    sell_price = future_data[code]["close"].iloc[-1]
                    profit = (sell_price - buy_price) / buy_price

                    rsi_val = score_obj.momentum.get("rsi", 0)

                    results.append(
                        {
                            "code": code,
                            "date": target_date,
                            "score": round(score_obj.score, 2),
                            "decision": decision,
                            "rsi": round(rsi_val, 1),
                            "return": f"{profit:.2%}",
                            "result_msg": (
                                "성공(수익)"
                                if decision == "매수" and profit > 0
                                else (
                                    "실패(손실)"
                                    if decision == "매수" and profit < 0
                                    else (
                                        "성공(손실회피)"
                                        if decision != "매수" and profit < 0
                                        else "아쉬움(기회비용)"
                                    )
                                )
                            ),
                        }
                    )
                except IndexError:
                    pass

    return {"backtest_result": results}
