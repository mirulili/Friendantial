import re
import asyncio
import logging
from datetime import datetime
from typing import Optional, List

import httpx
from fastapi import HTTPException, Request, Depends
from sqlalchemy.orm import Session

from .config import TZ, MARKET, NEWS_MAX
from .models import RecoItem, RecoResponse, FeatureConf, StockScore
from .universe import get_universe
from .market_data import fetch_ohlcv
from .database import get_db
from .db_models import RecommendationRun, RecommendedStock
from .sentiment import fetch_news_titles, analyze_news_sentiment
from .scoring import compute_features, score_stock
import pandas as pd

def calculate_stock_stars(score: float, market_regime: str) -> int:
    """종합 점수와 시장 상황을 바탕으로 1~5점의 별점을 부여합니다."""
    # 100점 만점 기준으로 별점 기준 조정
    thresholds = {
        "BULL":    [60, 70, 80, 90],  # 상승장: 별점 후하게
        "NEUTRAL": [65, 75, 85, 95],  # 중립장: 보통
        "BEAR":    [70, 80, 90, 97],  # 하락장: 별점 짜게
    }.get(market_regime, [65, 75, 85, 95])

    if score >= thresholds[3]:
        return 5
    if score >= thresholds[2]:
        return 4
    if score >= thresholds[1]:
        return 3
    if score >= thresholds[0]:
        return 2
    return 1

async def recommend(request: Request, as_of: Optional[str] = None, n: int = 5, with_news: bool = True, strategy: str = "default", db: Session = Depends(get_db)) -> RecoResponse:
    if as_of is None:
        as_of = datetime.now(TZ).date().isoformat()
    
    universe = await get_universe(request, 'KOSPI' if MARKET.upper() == 'KS' else 'KOSDAQ')
    if not universe:
        raise HTTPException(status_code=503, detail="종목 유니버스를 가져올 수 없습니다.")

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
    pre_selected_codes = [s.code for s in pre_scored_stocks[:20]]
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
    # 뉴스 점수와 변동성을 Z-점수로 정규화하여 상대적 위치를 평가합니다.
    # Z-점수는 이상치에 덜 민감하여 안정적인 점수 산출에 유리합니다.

    # --- 뉴스 점수 Z-점수 정규화 ---
    all_news_scores = [news_data_map.get(code, {}).get("score", 0.0) for code in pre_selected_codes if code in news_data_map]
    news_score_series = pd.Series(all_news_scores)
    news_mean = news_score_series.mean()
    news_std = news_score_series.std()

    def get_news_z_score(score):
        if news_std > 0:
            return (score - news_mean) / news_std
        return 0.0 # 모든 점수가 동일하면 Z-점수는 0

    # --- 변동성 Z-점수 정규화 ---
    volatility_scores = [
        float(features_map[code]["ret1"].rolling(20).std().iloc[-2])
        for code in pre_selected_codes if code in features_map
    ]
    vol_series = pd.Series(volatility_scores)
    vol_mean = vol_series.mean()
    vol_std = vol_series.std()

    def get_volatility_z_score(vol):
        if vol_std > 0:
            # 변동성은 낮을수록 좋으므로 Z-점수에 음수를 취해 페널티로 작용하도록 합니다.
            # (높은 변동성 -> 높은 Z-점수 -> 점수 하락)
            return (vol - vol_mean) / vol_std
        return 0.0 # 모든 변동성이 동일하면 Z-점수는 0

    # --- 4단계: 최종 점수 계산 및 순위 결정 ---
    raw_scored_stocks: List[StockScore] = []
    for code, feat in features_map.items():
        if feat.empty:
            continue
        
        analysis = news_data_map.get(code, {"score": 0.0}) if with_news else {"score": 0.0}
        raw_news_score = float(analysis.get("score", 0.0))
        news_z_score = get_news_z_score(raw_news_score)

        # Z-점수로 정규화된 변동성 점수를 사용합니다.
        raw_volatility = float(feat["ret1"].rolling(20).std().iloc[-2])
        volatility_z_score = get_volatility_z_score(raw_volatility)
        
        s = score_stock(
            code, 
            code_to_name_map.get(code, code), 
            feat, 
            get_z_scores(feat),
            news_z_score, 
            volatility_z_score, 
            conf, 
            market_regime=market_regime,
            strategy=strategy # strategy 파라미터 전달
        )
        if s:
            raw_scored_stocks.append(s)

    if not raw_scored_stocks:
        raise HTTPException(status_code=503, detail="Insufficient data for scoring")

    # --- 5단계: 점수 스케일링 (0-100점 만점) ---
    all_raw_scores = [s.score for s in raw_scored_stocks]
    min_raw_score, max_raw_score = min(all_raw_scores), max(all_raw_scores)

    def scale_to_100(score: float) -> int:
        if max_raw_score > min_raw_score:
            # 점수를 0-1 사이로 정규화한 후 100을 곱합니다.
            # 하위 20%는 0~60점, 상위 80%는 60~100점에 분포하도록 조정하여 변별력을 높입니다.
            normalized = (score - min_raw_score) / (max_raw_score - min_raw_score)
            if normalized < 0.2:
                return int(normalized / 0.2 * 60)
            else:
                return int(60 + (normalized - 0.2) / 0.8 * 40)
        return 50 # 모든 점수가 동일할 경우 50점 부여

    scored: List[RecoItem] = []
    for s in raw_scored_stocks:
        final_score = scale_to_100(s.score)
        stars = calculate_stock_stars(final_score, market_regime)
        news_summary = news_data_map.get(s.code) if with_news else None
        scored.append(RecoItem(code=s.code, name=s.name, score=final_score, stars=stars, weight=0.0, reason=s.reason, momentum=s.momentum, news_sentiment=news_summary))

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
                news_sentiment=item.news_sentiment.model_dump() if item.news_sentiment and hasattr(item.news_sentiment, 'model_dump') else None
            )
            db.add(stock)
        db.commit()
    except Exception as e:
        logging.error("추천 결과 저장 실패: %s", e)
        db.rollback()

    return RecoResponse(as_of=as_of, candidates=top)