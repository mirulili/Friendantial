import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import MARKET, NEWS_MAX, TZ
from ..db.database import get_db
from ..db.db_models import RecommendationRun, RecommendedStock
from ..schemas.models import FeatureConf, RecoItem, RecoResponse
from ..services.market_data import fetch_ohlcv
from ..services.sentiment import analyze_news_sentiment, fetch_news_titles
from ..services.universe import get_universe

from .market_analysis import determine_market_regime
from .presentation import calculate_stock_stars, generate_friendly_reason, scale_to_100
from .scoring import compute_features, score_stock


async def recommend(
    request: Request,
    as_of: Optional[str] = None,
    n: int = 5,
    with_news: bool = True,
    strategy: str = "default",
    db: Session = Depends(get_db),
) -> RecoResponse:
    if as_of is None:
        as_of = datetime.now(TZ).date().isoformat()

    # 1. 유니버스 및 데이터 수집
    universe = await get_universe(
        request, "KOSPI" if MARKET.upper() == "KS" else "KOSDAQ"
    )
    if not universe:
        raise HTTPException(
            status_code=503, detail="종목 유니버스를 가져올 수 없습니다."
        )

    codes, names_list = zip(*universe)
    code_to_name_map = dict(zip(codes, names_list))
    data = await fetch_ohlcv(request, list(codes), end_date=as_of, lookback_days=120)
    conf = FeatureConf()

    # 2. 시장 상황 분석 (분리된 모듈 사용)
    market_regime = await determine_market_regime(request, as_of)

    # 3. 피쳐 계산 및 모멘텀 통계 산출
    features_map = {}
    mom_values = {f"mom{p}": [] for p in [conf.mom_short, conf.mom_med, conf.mom_long]}

    for code in codes:
        df = data.get(code)
        if df is not None and not df.empty and len(df) >= conf.mom_long + 2:
            features_map[code] = compute_features(df, conf)
            # 모멘텀 통계 수집
            prev = features_map[code].iloc[-2]
            for k in mom_values.keys():
                mom_values[k].append(float(prev.get(k, 0.0)))

    # Z-Score 계산을 위한 통계치
    mom_stats = {
        key: (pd.Series(vals).mean(), pd.Series(vals).std())
        for key, vals in mom_values.items()
    }

    # 4. 1차 스코어링 (Z-Score 기반)
    pre_scored_stocks = []
    for code, feat in features_map.items():
        # 개별 종목 Z-Score 계산 (Inline Logic)
        z_scores = {}
        prev = feat.iloc[-2]
        for key, (mean, std) in mom_stats.items():
            z_scores[key] = (float(prev.get(key, 0.0)) - mean) / std if std > 0 else 0.0

        stock_score = score_stock(
            code,
            code_to_name_map.get(code, code),
            feat,
            z_scores,
            0.0,
            0.0,
            conf,
            market_regime,
            strategy,
        )
        if stock_score:
            pre_scored_stocks.append(stock_score)

    if not pre_scored_stocks:
        raise HTTPException(status_code=503, detail="채점 가능한 종목이 없습니다.")

    # 상위 종목 선별 (뉴스 분석용)
    pre_scored_stocks.sort(key=lambda x: x.score, reverse=True)
    pre_selected_codes = [s.code for s in pre_scored_stocks[:20]]

    # 5. 뉴스 감성 분석
    news_data_map = {}
    if with_news:
        async with httpx.AsyncClient() as client:
            all_titles = []
            batch_size = 5
            for i in range(0, len(pre_selected_codes), batch_size):
                batch_codes = pre_selected_codes[i : i + batch_size]
                tasks = [
                    fetch_news_titles(
                        client, code_to_name_map.get(code) or code, limit=NEWS_MAX
                    )
                    for code in batch_codes
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                all_titles.extend(batch_results)
                await asyncio.sleep(1)

            sentiment_pipe = request.app.state.sentiment_pipe
            for code, titles in zip(pre_selected_codes, all_titles):
                if isinstance(titles, list) and titles:
                    news_data_map[code] = analyze_news_sentiment(sentiment_pipe, titles)
                else:
                    news_data_map[code] = {
                        "score": 0.0,
                        "summary": "뉴스 없음",
                        "details": [],
                    }

    # 6. 최종 스코어링 (뉴스, 변동성 반영)
    # 뉴스/변동성 점수 정규화 통계 준비
    news_scores = [
        news_data_map.get(c, {}).get("score", 0.0) for c in pre_selected_codes
    ]
    vol_scores = [
        float(features_map[c]["ret1"].rolling(20).std().iloc[-2])
        for c in pre_selected_codes
    ]

    news_mean, news_std = pd.Series(news_scores).mean(), pd.Series(news_scores).std()
    vol_mean, vol_std = pd.Series(vol_scores).mean(), pd.Series(vol_scores).std()

    raw_scored_stocks = []
    for code in pre_selected_codes:
        feat = features_map[code]

        # 뉴스 Z-Score
        n_score = news_data_map.get(code, {}).get("score", 0.0)
        n_z = (n_score - news_mean) / news_std if news_std > 0 else 0.0

        # 변동성 Z-Score
        v_val = float(feat["ret1"].rolling(20).std().iloc[-2])
        v_z = (v_val - vol_mean) / vol_std if vol_std > 0 else 0.0

        # 모멘텀 Z-Score (구조상 다시 재계산 생성)
        z_scores = {}
        prev = feat.iloc[-2]
        for key, (mean, std) in mom_stats.items():
            z_scores[key] = (float(prev.get(key, 0.0)) - mean) / std if std > 0 else 0.0

        s = score_stock(
            code,
            code_to_name_map.get(code, code),
            feat,
            z_scores,
            n_z,
            v_z,
            conf,
            market_regime,
            strategy,
        )
        if s:
            raw_scored_stocks.append(s)

    # 7. 결과 생성 (프레젠테이션 로직 사용)
    all_raw_scores = [s.score for s in raw_scored_stocks]
    min_raw, max_raw = min(all_raw_scores), max(all_raw_scores)

    scored = []
    for s in raw_scored_stocks:
        final_score = scale_to_100(s.score, min_raw, max_raw, market_regime)
        friendly_reason = generate_friendly_reason(s)

        temp_item = RecoItem(
            code=s.code,
            name=s.name,
            score=final_score,
            stars=0,
            weight=0.0,
            price=s.price,
            reason=friendly_reason,
            momentum=s.momentum,
            news_sentiment=news_data_map.get(s.code) if with_news else None,
        )
        temp_item.stars = calculate_stock_stars(temp_item, market_regime)
        scored.append(temp_item)

    scored.sort(key=lambda x: x.score, reverse=True)
    top = scored[:n]
    for item in top:
        item.weight = 1.0 / len(top)

    # 8. DB 저장
    _save_recommendation_to_db(db, as_of, top)

    return RecoResponse(as_of=as_of, candidates=top)


def _save_recommendation_to_db(db, as_of, items):
    """DB 저장 로직 분리"""
    try:
        run = RecommendationRun(as_of=datetime.strptime(as_of, "%Y-%m-%d").date())
        db.add(run)
        db.flush()
        for item in items:
            stock = RecommendedStock(
                run_id=run.id,
                code=item.code,
                name=item.name,
                score=item.score,
                weight=item.weight,
                reason=item.reason,
                momentum=item.momentum,
                news_sentiment=(
                    item.news_sentiment.model_dump()
                    if item.news_sentiment
                    and hasattr(item.news_sentiment, "model_dump")
                    else None
                ),
            )
            db.add(stock)
        db.commit()
    except Exception as e:
        logging.error(f"DB 저장 실패: {e}")
        db.rollback()
