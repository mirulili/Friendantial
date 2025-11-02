from typing import Optional

from fastapi import APIRouter, Query

from app.core import recommend
from app.models import RecoResponse

# APIRouter 인스턴스 생성
router = APIRouter(
    tags=["recommendations"],  # API 문서에서 'recommendations' 그룹으로 묶음
)


@router.get("/recommendations", response_model=RecoResponse)
async def get_recommendations(
    as_of: Optional[str] = Query(None, description="기준일 (YYYY-MM-DD)"),
    n: int = Query(5, ge=1, le=10, description="추천할 종목 수"),
    with_news: bool = Query(True, description="뉴스 감성 분석 포함 여부"),
):
    """모멘텀, 거래량, 뉴스 감성 점수를 종합하여 주식 종목을 추천합니다."""
    return await recommend(as_of=as_of, n=n, with_news=with_news)