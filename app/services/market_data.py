import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
import pandas as pd
import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from ..config import DATA_GO_KR_API_KEY, TZ, UNIVERSE_MIN_TURNOVER_WON


async def fetch_ohlcv(
    request: Request,
    codes: List[str],
    end_date: Optional[str] = None,
    lookback_days: int = 120,
) -> Dict[str, pd.DataFrame]:
    """공공데이터포털 API를 사용하여 여러 종목의 OHLCV 데이터를 비동기적으로 가져옵니다."""
    if end_date is None:
        end_date = datetime.now(TZ).date().isoformat()
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid as_of date '{end_date}'; expected YYYY-MM-DD",
        )
    start_dt = end_dt - timedelta(days=max(lookback_days, 30))

    if not DATA_GO_KR_API_KEY:
        logging.error("DATA_GO_KR_API_KEY가 설정되지 않았습니다.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key is not configured.",
        )

    dates_to_fetch = [
        start_dt + timedelta(days=i) for i in range((end_dt - start_dt).days + 1)
    ]
    all_rows = []
    redis_conn = request.app.state.redis

    async with httpx.AsyncClient() as client:
        tasks = []
        for date in dates_to_fetch:
            # 주말은 API 호출에서 제외
            if date.weekday() >= 5:  # 5: Saturday, 6: Sunday
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
    numeric_cols = ["clpr", "hipr", "lopr", "mkp", "trqu", "trPrc"]
    for col in numeric_cols:
        full_df[col] = pd.to_numeric(full_df[col], errors="coerce")

    # yfinance 티커 형식('######.KS')을 공공데이터포털 형식('######')으로 미리 변환
    code_mapping = {code: code.split(".")[0] for code in codes}

    out: Dict[str, pd.DataFrame] = {}
    for code, clean_code in code_mapping.items():
        df = full_df[full_df["srtnCd"] == clean_code].copy()
        if df.empty:
            out[code] = pd.DataFrame()
            continue

        df = df.rename(
            columns={
                "basDt": "date",
                "mkp": "open",
                "hipr": "high",
                "lopr": "low",
                "clpr": "close",
                "trqu": "volume",
                "trPrc": "value_traded",
            }
        )
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        keep = [
            c
            for c in ["open", "high", "low", "close", "volume", "value_traded"]
            if c in df.columns
        ]
        df = df[keep].sort_index()
        out[code] = df
    return out


async def _fetch_daily_prices(
    client: httpx.AsyncClient, redis_conn: redis.Redis, date: datetime.date
) -> List[Dict]:
    """특정 날짜의 모든 종목 시세 데이터를 가져옵니다."""
    cache_key = f"market-data:{date.strftime('%Y%m%d')}"

    # 당일 데이터는 변동 가능성이 있으므로 캐시하지 않고, 과거 데이터만 캐시를 확인
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
    all_items = []
    page_no = 1

    while True:
        params = {
            "serviceKey": DATA_GO_KR_API_KEY,
            "basDt": date.strftime("%Y%m%d"),
            "resultType": "json",
            "numOfRows": 1000,
            "pageNo": page_no,
        }
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            items = (
                data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
            )

            if not items:
                break  # 더 이상 데이터가 없으면 루프 종료

            all_items.extend(items)

            # 마지막 페이지인지 확인
            total_count = int(
                data.get("response", {}).get("body", {}).get("totalCount", 0)
            )
            if page_no * params["numOfRows"] >= total_count:
                break

            page_no += 1
            await asyncio.sleep(0.1)  # 짧은 딜레이로 API 서버 부하 감소

        except Exception as e:
            logging.error(
                "공공데이터 API 호출 실패 (date: %s, page: %s): %s", date, page_no, e
            )
            # 한 페이지 실패 시, 현재까지 수집된 데이터만 반환
            break

    if is_past_date and all_items:
        try:
            # 과거 데이터는 7일간 캐시
            await redis_conn.set(
                cache_key,
                json.dumps(all_items),
                ex=int(timedelta(days=7).total_seconds()),
            )
        except Exception as e:
            logging.error("Redis cache write error: %s", e)

    return all_items


async def _fetch_stock_info(
    client: httpx.AsyncClient, redis_conn: redis.Redis, stock_code: str
) -> Optional[Dict]:
    """특정 종목의 최신 정보를 공공데이터 API를 통해 가져옵니다. 결과는 1일간 캐시됩니다."""
    clean_code = stock_code.split(".")[0]
    cache_key = f"stock-info:{clean_code}"

    # 1. Redis 캐시 확인
    try:
        cached_data = await redis_conn.get(cache_key)
        if cached_data:
            logging.debug("Reading stock info from Redis cache: %s", cache_key)
            return json.loads(cached_data)
    except Exception as e:
        logging.warning(
            "Redis cache read error for stock info, fetching from API: %s", e
        )

    # 2. 캐시 없으면 API 호출
    latest_prices = await get_latest_daily_prices(client, redis_conn)
    for item in latest_prices or []:
        if item.get("srtnCd") == clean_code:
            try:
                await redis_conn.set(
                    cache_key,
                    json.dumps(item),
                    ex=int(timedelta(days=1).total_seconds()),
                )
            except Exception as e:
                logging.error("Redis cache write error for stock info: %s", e)
            return item
    return None


async def get_latest_daily_prices(
    client: httpx.AsyncClient, redis_conn: redis.Redis
) -> List[Dict]:
    """최근 5일 중 가장 최신 거래일의 전체 시세 데이터를 반환합니다."""
    for i in range(5):
        date_to_check = datetime.now(TZ).date() - timedelta(days=i)
        if date_to_check.weekday() >= 5:  # 주말 제외
            continue

        daily_prices = await _fetch_daily_prices(client, redis_conn, date_to_check)
        if daily_prices:
            logging.info(f"Found latest daily prices for date: {date_to_check}")
            return daily_prices
    return []


async def get_universe_from_market_data(
    request: Request, market_code: str
) -> List[Tuple[str, str]]:
    """
    공공데이터포털 API를 통해 조회한 최신 시장 데이터를 기반으로 유니버스를 생성합니다.
    """
    redis_conn = request.app.state.redis
    async with httpx.AsyncClient() as client:
        daily_prices = await get_latest_daily_prices(client, redis_conn)

        if not daily_prices:
            return []  # 5일간 데이터를 찾지 못하면 빈 리스트 반환

        universe = []
        suffix = ".KS" if market_code.upper() == "KOSPI" else ".KQ"

        for item in daily_prices:
            # 거래대금(trPrc)을 기준으로 필터링
            turnover = float(item.get("trPrc", 0))
            if turnover < UNIVERSE_MIN_TURNOVER_WON:
                continue

            # 시장 구분(mrktCtg)을 기준으로 필터링
            if item.get("mrktCtg") == market_code.upper():
                code = item.get("srtnCd")
                name = item.get("itmsNm")
                if code and name:
                    # yfinance 형식에 맞게 접미사 추가
                    universe.append((f"{code}{suffix}", name))

        msg = (
            f"총 {len(daily_prices)}개 종목 중 거래대금 및 시장 기준을 만족하는 "
            f"{len(universe)}개 종목으로 유니버스를 확정합니다."
        )
        logging.info(msg)
        return universe
