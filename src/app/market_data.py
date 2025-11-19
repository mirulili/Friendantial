import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pathlib import Path
import pandas as pd
import httpx
from fastapi import HTTPException, status, Request
import redis.asyncio as redis
from typing import List, Tuple
from .config import TZ, DATA_GO_KR_API_KEY, UNIVERSE_MIN_TURNOVER_WON

async def fetch_ohlcv(request: Request, codes: List[str], end_date: Optional[str] = None, lookback_days: int = 120) -> Dict[str, pd.DataFrame]:
    """공공데이터포털 API를 사용하여 여러 종목의 OHLCV 데이터를 비동기적으로 가져옵니다."""
    if end_date is None:
        end_date = datetime.now(TZ).date().isoformat()
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid as_of date '{end_date}'; expected YYYY-MM-DD")
    start_dt = end_dt - timedelta(days=max(lookback_days, 30))

    if not DATA_GO_KR_API_KEY:
        logging.error("DATA_GO_KR_API_KEY가 설정되지 않았습니다.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API key is not configured.")

    dates_to_fetch = [start_dt + timedelta(days=i) for i in range((end_dt - start_dt).days + 1)]
    all_rows = []
    redis_conn = request.app.state.redis

    async with httpx.AsyncClient() as client:
        tasks = []
        for date in dates_to_fetch:
            # 주말은 API 호출에서 제외하여 효율성 증대
            if date.weekday() >= 5: # 5: Saturday, 6: Sunday
                continue
            tasks.append(_fetch_daily_prices(client, redis_conn, date))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                all_rows.extend(res)
            elif isinstance(res, Exception):
                logging.warning("Failed to fetch daily prices: %s", res)

    if not all_rows:
        logging.warning("API로부터 어떠한 데이터도 가져오지 못했습니다.")
        return {code: pd.DataFrame() for code in codes}

    full_df = pd.DataFrame(all_rows)
    # API 응답의 숫자 필드는 문자열이므로 숫자 형태로 변환
    numeric_cols = ['clpr', 'hipr', 'lopr', 'mkp', 'trqu', 'trPrc']
    for col in numeric_cols:
        full_df[col] = pd.to_numeric(full_df[col], errors='coerce')

    out: Dict[str, pd.DataFrame] = {}
    for code in codes:
        # yfinance의 티커 형식(예: '005930.KS')을 공공데이터포털 형식('005930')으로 변환
        clean_code = code.split('.')[0]
        df = full_df[full_df['srtnCd'] == clean_code].copy()
        if df.empty:
            out[code] = pd.DataFrame()
            continue

        df = df.rename(columns={"basDt": "date", "mkp": "open", "hipr": "high", "lopr": "low", "clpr": "close", "trqu": "volume", "trPrc": "value_traded"})
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        keep = [c for c in ["open", "high", "low", "close", "volume", "value_traded"] if c in df.columns]
        df = df[keep].sort_index()
        out[code] = df
    return out

async def _fetch_daily_prices(client: httpx.AsyncClient, redis_conn: redis.Redis, date: datetime.date) -> List[Dict]:
    """특정 날짜의 모든 종목 시세 데이터를 가져옵니다."""
    cache_key = f"market-data:{date.strftime('%Y%m%d')}"

    # 당일 데이터는 변동 가능성이 있으므로 캐시하지 않고, 과거 데이터만 캐시를 확인합니다.
    is_past_date = date < datetime.now(TZ).date()

    if is_past_date:
        try:
            cached_data = await redis_conn.get(cache_key)
            if cached_data:
                logging.debug("Reading from Redis cache: %s", cache_key)
                return json.loads(cached_data)
        except Exception as e:
            logging.warning("Redis cache read error, fetching from API: %s", e)

    url = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "basDt": date.strftime("%Y%m%d"),
        "resultType": "json",
        "numOfRows": 100, # 하루 전체 종목 수를 감당할 수 있는 큰 값으로 설정
    }
    try:
        resp = await client.get(url, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

        if is_past_date and items:
            try:
                # 과거 데이터는 7일간 캐시
                await redis_conn.set(cache_key, json.dumps(items), ex=timedelta(days=7).total_seconds())
            except Exception as e:
                logging.error("Redis cache write error: %s", e)
        return items
    except Exception as e:
        logging.error("공공데이터 API 호출 실패 (date: %s): %s", date, e)
        return []

async def get_universe_from_market_data(request: Request, market_code: str) -> List[Tuple[str, str]]:
    """
    공공데이터포털 API를 통해 조회한 최신 시장 데이터를 기반으로 유니버스를 생성합니다.
    pykrx에 대한 의존성을 제거하고, 실제 거래 데이터를 기반으로 유니버스를 구성합니다.
    """
    redis_conn = request.app.state.redis
    async with httpx.AsyncClient() as client:
        # 최근 5일간의 데이터를 확인하여 가장 최신 거래일을 찾습니다.
        for i in range(5):
            date_to_check = datetime.now(TZ).date() - timedelta(days=i)
            if date_to_check.weekday() >= 5: # 주말 제외
                continue

            logging.info(f"{date_to_check} 데이터로 유니버스 생성을 시도합니다.")
            daily_prices = await _fetch_daily_prices(client, redis_conn, date_to_check)

            if not daily_prices:
                continue

            universe = []
            suffix = ".KS" if market_code.upper() == "KOSPI" else ".KQ"
            
            for item in daily_prices:
                # 거래대금(trPrc)을 기준으로 필터링
                turnover = float(item.get('trPrc', 0))
                if turnover < UNIVERSE_MIN_TURNOVER_WON:
                    continue
                
                # 시장 구분(mrktCtg)을 기준으로 필터링
                if item.get('mrktCtg') == market_code.upper():
                    code = item.get('srtnCd')
                    name = item.get('itmsNm')
                    if code and name:
                        # yfinance 형식에 맞게 접미사 추가
                        universe.append((f"{code}{suffix}", name))
            
            if universe:
                logging.info(f"총 {len(daily_prices)}개 종목 중 거래대금 및 시장 기준을 만족하는 {len(universe)}개 종목으로 유니버스를 확정합니다.")
                return universe
    return [] # 5일간 데이터를 찾지 못하면 빈 리스트 반환