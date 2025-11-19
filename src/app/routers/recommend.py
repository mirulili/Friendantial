from typing import Optional

from fastapi import APIRouter, Query, Request, Depends

from app.core import recommend
from app.models import RecoResponse

# APIRouter 인스턴스 생성
router = APIRouter(
    tags=["recommendations"],  # API 문서에서 'recommendations' 그룹으로 묶음
)


@router.get("/recommendations", response_model=RecoResponse, summary="종합 주식 추천")
async def get_recommendations(
    recommendations: RecoResponse = Depends(recommend)
):
    """
    모멘텀, 거래량, 뉴스 감성 점수 및 시장 상황을 종합하여 상위 주식 종목을 추천합니다.
    
    FastAPI의 의존성 주입 시스템을 통해 `core.recommend` 함수를 직접 호출하여 결과를 반환합니다.
    """
    return recommendations