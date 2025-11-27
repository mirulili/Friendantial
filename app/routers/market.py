from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_http_client
from app.services.market_data import _fetch_stock_info, fetch_ohlcv

router = APIRouter(
    prefix="/market-data",
    tags=["market-data"],
)


@router.get("/lookup/{stock_code}", summary="종목 정보 조회 (코드 -> 이름 변환)")
async def lookup_stock_info(
    request: Request,
    stock_code: str,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    주어진 종목 코드(예: 005930.KS)에 해당하는 종목명, 시장 구분 등의 정보를 반환합니다.
    내부적으로 캐싱이 적용되어 반복 호출 시 빠릅니다.
    """
    redis_conn = request.app.state.redis
    stock_info = await _fetch_stock_info(client, redis_conn, stock_code)

    if not stock_info:
        raise HTTPException(
            status_code=404, detail=f"종목 정보를 찾을 수 없습니다: {stock_code}"
        )

    return {
        "code": stock_code,
        "name": stock_info.get("itmsNm"),
        "market": stock_info.get("mrktCtg"),
        **stock_info,
    }


@router.get("/ohlcv/{stock_code}", summary="종목 시세(OHLCV) 조회")
async def get_ohlcv_for_stock(
    request: Request,
    stock_code: str,
    lookback_days: int = 120,
    end_date: Optional[str] = None,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """주어진 종목 코드에 대한 OHLCV(시가, 고가, 저가, 종가, 거래량) 데이터를 반환합니다."""
    data = await fetch_ohlcv(
        client, request, [stock_code], end_date=end_date, lookback_days=lookback_days
    )
    df = data.get(stock_code)
    return df.to_dict(orient="index") if df is not None and not df.empty else {}
