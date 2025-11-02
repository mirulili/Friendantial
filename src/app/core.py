import re
import asyncio
import logging
from datetime import datetime
from typing import Optional, List

import httpx
from fastapi import HTTPException

from .config import TZ, MARKET, NEWS_MAX
from .models import RecoItem, RecoResponse, FeatureConf
from .universe import get_universe
from .market_data import fetch_ohlcv
from .sentiment import fetch_news_titles, analyze_news_sentiment
from .scoring import compute_features, score_stock

async def recommend(as_of: Optional[str] = None, n: int = 5, with_news: bool = True) -> RecoResponse:
    if as_of is None:
        as_of = datetime.now(TZ).date().isoformat()
    
    universe = get_universe('KOSPI' if MARKET.upper() == 'KS' else 'KOSDAQ')
    codes, names_list = zip(*universe)
    names = dict(zip(codes, names_list))
    
    data = fetch_ohlcv(list(codes), end_date=as_of, lookback_days=120)
    conf = FeatureConf()

    news_data_map = {}
    if with_news:
        async with httpx.AsyncClient() as client:
            tasks = []
            valid_codes_for_news = [code for code, df in data.items() if df is not None and not df.empty]
            for code in valid_codes_for_news:
                qname = names.get(code) or re.sub(r"\.[A-Z]{2}$", "", code)
                tasks.append(fetch_news_titles(client, qname, limit=NEWS_MAX))
            
            all_titles = await asyncio.gather(*tasks, return_exceptions=True)

            for code, titles_result in zip(valid_codes_for_news, all_titles):
                if isinstance(titles_result, list):
                    news_data_map[code] = analyze_news_sentiment(titles_result)
                else:
                    logging.warning(f"News fetch failed for {code}: {titles_result}")
                    news_data_map[code] = {"score": 0.0, "summary": "Failed to fetch news", "details": []}

    scored: List[RecoItem] = []
    for code, df in data.items():
        if df.empty:
            continue
        
        analysis = news_data_map.get(code, {"score": 0.0}) if with_news else {"score": 0.0}
        news_score = float(analysis.get("score", 0.0))
        news_summary = {"summary": analysis.get("summary"), "details": analysis.get("details")} if with_news else None
        
        feat = compute_features(df, conf)
        s = score_stock(code, names.get(code, code), feat, news_score, conf)
        if s:
            scored.append(RecoItem(code=s.code, name=s.name, score=s.score, weight=0.0, reason=s.reason, momentum=s.momentum, news_sentiment=news_summary))

    if not scored:
        raise HTTPException(status_code=503, detail="Insufficient data for scoring")

    scored.sort(key=lambda x: x.score, reverse=True)
    top = scored[:n]
    for item in top:
        item.weight = 1.0 / len(top)

    return RecoResponse(as_of=as_of, candidates=top)