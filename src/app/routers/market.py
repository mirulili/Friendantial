from typing import Optional

from fastapi import APIRouter

from app.market_data import fetch_ohlcv

router = APIRouter(
    prefix="/market-data",
    tags=["market-data"],
)


@router.get("/ohlcv/{stock_code}", summary="종목 시세(OHLCV) 조회")
async def get_ohlcv_for_stock(
    stock_code: str,
    lookback_days: int = 120,
    end_date: Optional[str] = None,
):
    """주어진 종목 코드에 대한 OHLCV(시가, 고가, 저가, 종가, 거래량) 데이터를 반환합니다."""
    data = fetch_ohlcv([stock_code], end_date=end_date, lookback_days=lookback_days)
    df = data.get(stock_code)
    return df.to_dict(orient="index") if df is not None and not df.empty else {}