from fastapi import APIRouter
from app.models import RecoResponse

router = APIRouter(
    prefix="/reporting",
    tags=["reporting"],
)


@router.post("/summary", summary="추천 결과 요약 보고서 생성")
async def create_recommendation_report(reco_response: RecoResponse):
    """
    추천 결과(RecoResponse)를 입력받아 요약 보고서를 생성합니다.
    """
    if not reco_response.candidates:
        return {"report": "추천된 종목이 없습니다."}

    report_parts = [f"## {reco_response.as_of} 기준 주식 추천 보고서"]
    report_parts.append(f"\n총 {len(reco_response.candidates)}개 종목을 추천합니다.\n")

    for i, stock in enumerate(reco_response.candidates, 1):
        part = (
            f"{i}. **{stock.name} ({stock.code})**\n"
            f"   - 추천 점수: {stock.score:.2f}\n"
            f"   - 주요 근거: {stock.reason}"
        )
        report_parts.append(part)

    return {"report": "\n".join(report_parts)}