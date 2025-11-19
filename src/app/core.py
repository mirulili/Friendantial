import re
import asyncio
import logging
from datetime import datetime
from typing import Optional, List

import httpx
from fastapi import HTTPException, Request, Depends
from sqlalchemy.orm import Session

from .config import TZ, MARKET, NEWS_MAX
from .models import RecoItem, RecoResponse, FeatureConf
from .universe import get_universe
from .market_data import fetch_ohlcv
from .database import get_db
from .db_models import RecommendationRun, RecommendedStock
from .sentiment import fetch_news_titles, analyze_news_sentiment
from .scoring import compute_features, score_stock
import pandas as pd

def get_stars_for_stock(news_score: float) -> int:
    """종합 뉴스 점수를 바탕으로 1~5점의 별점을 부여합니다."""
    if news_score >= 1.5:
        return 5
    if news_score >= 0.5:
        return 4
    if news_score <= -1.5:
        return 1
    if news_score <= -0.5:
        return 2
    return 3

async def recommend(request: Request, as_of: Optional[str] = None, n: int = 5, with_news: bool = True, db: Session = Depends(get_db)) -> RecoResponse:
    if as_of is None:
        as_of = datetime.now(TZ).date().isoformat()
    
    universe = await get_universe(request, 'KOSPI' if MARKET.upper() == 'KS' else 'KOSDAQ')
    if not universe:
        raise HTTPException(status_code=503, detail="종목 유니버스를 가져올 수 없습니다. pykrx 또는 외부 API의 일시적인 문제일 수 있습니다.")

    codes, names_list = zip(*universe)
    code_to_name_map = dict(zip(codes, names_list))
    
    data = await fetch_ohlcv(request, list(codes), end_date=as_of, lookback_days=120)
    conf = FeatureConf()

    # --- 시장 상황(Market Regime) 판단 로직 구현 ---
    # 시장 대표 ETF의 20일 이동평균선을 기준으로 상승/하락장을 판단합니다.
    market_regime = "NEUTRAL"  # 기본값은 중립
    market_index_ticker = "069500.KS" if MARKET.upper() == 'KS' else "229200.KS" # KOSPI: KODEX 200, KOSDAQ: KODEX KOSDAQ 150
    try:
        market_index_data = await fetch_ohlcv(request, [market_index_ticker], end_date=as_of, lookback_days=30)
        df_index = market_index_data.get(market_index_ticker)

        if df_index is not None and not df_index.empty and len(df_index) >= 20:
            # 최근 종가와 20일 이동평균을 계산합니다.
            last_close = df_index["close"].iloc[-1]
            ma20 = df_index["close"].rolling(window=20).mean().iloc[-1]

            if last_close > ma20:
                market_regime = "BULL"
            else:
                market_regime = "BEAR"
            logging.info(f"시장 상황 판단: {market_regime} (종가: {last_close:.2f}, MA20: {ma20:.2f})")
    except Exception as e:
        logging.warning(f"시장 상황 판단 실패: {e}. 'NEUTRAL'로 진행합니다.")

    # --- 1단계: 모든 종목의 피쳐(모멘텀, 변동성) 계산 ---
    features_map = {}
    for code in codes:
        if (df := data.get(code)) is not None and not df.empty and len(df) >= conf.mom_long + 2:
            features_map[code] = compute_features(df, conf)

    # --- 모멘텀 Z-Score 계산 ---
    mom_periods = [conf.mom_short, conf.mom_med, conf.mom_long]
    mom_values = {f"mom{p}": [] for p in mom_periods}
    
    for code, feat_df in features_map.items():
        prev = feat_df.iloc[-2]
        for p in mom_periods:
            mom_values[f"mom{p}"].append(float(prev.get(f"mom{p}", 0.0)))

    mom_stats = {key: (pd.Series(vals).mean(), pd.Series(vals).std()) for key, vals in mom_values.items()}

    def get_z_scores(feat_df: pd.DataFrame) -> dict:
        z_scores = {}
        prev = feat_df.iloc[-2]
        for p in mom_periods:
            key = f"mom{p}"
            mean, std = mom_stats[key]
            if std > 0:
                z_scores[key] = (float(prev.get(key, 0.0)) - mean) / std
            else:
                z_scores[key] = 0.0
        return z_scores

    # Z-Score를 사용하여 사전 필터링
    pre_scored_stocks = [
        score_stock(code, code_to_name_map.get(code, code), feat, get_z_scores(feat), 0.0, 0.0, conf, market_regime)
        for code, feat in features_map.items()
    ]
    pre_scored_stocks = [s for s in pre_scored_stocks if s is not None]

    if not pre_scored_stocks:
        raise HTTPException(status_code=503, detail="모멘텀 점수를 계산할 종목이 부족합니다.")

    # 모멘텀 점수 상위 50개 종목을 1차 선별 (뉴스 분석 대상)
    pre_scored_stocks.sort(key=lambda x: x.score, reverse=True)
    pre_selected_codes = [s.code for s in pre_scored_stocks[:50]]
    logging.info(f"모멘텀 상위 {len(pre_selected_codes)}개 종목을 뉴스 분석 대상으로 확정합니다.")

    # --- 2단계: 선별된 종목에 대한 뉴스 감성 분석 ---
    sentiment_pipe = request.app.state.sentiment_pipe
    news_data_map = {}
    if with_news:
        async with httpx.AsyncClient() as client:
            # Naver API의 초당 요청 제한(rate limit)을 준수하기 위해 요청을 작은 배치로 나누어 보냅니다.
            # 5개씩 묶어서 요청하고, 각 배치 사이에 1초의 딜레이를 줍니다.
            all_titles = []
            batch_size = 5
            for i in range(0, len(pre_selected_codes), batch_size):
                batch_codes = pre_selected_codes[i:i+batch_size]
                tasks = []
                for code in batch_codes:
                    qname = code_to_name_map.get(code) or re.sub(r"\.[A-Z]{2}$", "", code)
                    tasks.append(fetch_news_titles(client, qname, limit=NEWS_MAX))
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                all_titles.extend(batch_results)
                await asyncio.sleep(1) # Rate limit을 피하기 위해 1초 대기

            for code, titles_result in zip(pre_selected_codes, all_titles):
                if isinstance(titles_result, list) and titles_result:
                    news_data_map[code] = analyze_news_sentiment(sentiment_pipe, titles_result)
                elif isinstance(titles_result, list) and not titles_result:
                    # 뉴스를 찾지 못한 경우, news_data_map에 추가하지 않아 추천 대상에서 제외되도록 합니다.
                    logging.info(f"뉴스를 찾을 수 없어 추천에서 제외: {code}")
                    # data 딕셔너리에서도 해당 종목을 제거하여 이후 분석에서 제외합니다.
                    data.pop(code, None)
                else:
                    logging.warning(f"News fetch failed for {code}: {titles_result}")
                    news_data_map[code] = {"score": 0.0, "summary": "Failed to fetch news", "details": []}

    # --- 3단계: 최종 점수 계산을 위한 정규화 ---
    # 모든 종목의 뉴스 점수를 수집하여 0과 1 사이로 정규화합니다.
    # 이를 통해 개별 종목의 뉴스 점수를 전체 유니버스 내에서 상대적으로 평가할 수 있습니다.
    all_news_scores = [news_data_map.get(code, {}).get("score", 0.0) for code in pre_selected_codes if code in news_data_map]
    min_score, max_score = min(all_news_scores) if all_news_scores else (0, 0), max(all_news_scores) if all_news_scores else (0, 0)
    
    def normalize_news_score(score):
        if max_score > min_score:
            return (score - min_score) / (max_score - min_score)
        return 0.5 # 모든 점수가 동일할 경우 중간값 반환

    # --- 변동성 점수 계산 및 정규화 준비 ---
    # 모든 종목의 피쳐와 변동성을 미리 계산합니다.
    volatility_scores = [
        float(features_map[code]["ret1"].rolling(20).std().iloc[-2])
        for code in pre_selected_codes if code in features_map
    ]

    min_vol, max_vol = min(volatility_scores) if volatility_scores else (0, 0), max(volatility_scores) if volatility_scores else (0, 0)

    def normalize_volatility(vol):
        if max_vol > min_vol:
            return (vol - min_vol) / (max_vol - min_vol)
        return 0.5 # 모든 변동성이 동일할 경우 중간값 반환

    # --- 4단계: 최종 점수 계산 및 순위 결정 ---
    scored: List[RecoItem] = []
    for code, feat in features_map.items():
        if feat.empty:
            continue
        
        analysis = news_data_map.get(code, {"score": 0.0}) if with_news else {"score": 0.0}
        raw_news_score = float(analysis.get("score", 0.0))
        normalized_news_score = normalize_news_score(raw_news_score)
        
        news_summary = None
        if with_news:
            stock_stars = get_stars_for_stock(raw_news_score)
            news_summary = {"summary": analysis.get("summary"), "stars": stock_stars, "details": analysis.get("details")}

        
        # 정규화된 변동성 점수를 사용합니다.
        raw_volatility = float(feat["ret1"].rolling(20).std().iloc[-2])
        normalized_volatility = normalize_volatility(raw_volatility)
        
        s = score_stock(
            code, 
            code_to_name_map.get(code, code), 
            feat, 
            get_z_scores(feat),
            normalized_news_score, 
            normalized_volatility, 
            conf, 
            market_regime=market_regime
        )
        if s:
            scored.append(RecoItem(code=s.code, name=s.name, score=s.score, weight=0.0, reason=s.reason, momentum=s.momentum, news_sentiment=news_summary))

    if not scored:
        raise HTTPException(status_code=503, detail="Insufficient data for scoring")

    scored.sort(key=lambda x: x.score, reverse=True)
    top = scored[:n]
    for item in top:
        item.weight = 1.0 / len(top)
    
    # --- 데이터베이스에 추천 결과 저장 ---
    try:
        run = RecommendationRun(as_of=datetime.strptime(as_of, "%Y-%m-%d").date())
        db.add(run)
        db.flush() # run 객체의 id를 할당받기 위해 flush

        for item in top:
            stock = RecommendedStock(
                run_id=run.id,
                code=item.code,
                name=item.name,
                score=item.score,
                weight=item.weight,
                reason=item.reason,
                momentum=item.momentum,
                news_sentiment=item.news_sentiment
            )
            db.add(stock)
        db.commit()
    except Exception as e:
        logging.error("추천 결과 저장 실패: %s", e)
        db.rollback()

    return RecoResponse(as_of=as_of, candidates=top)