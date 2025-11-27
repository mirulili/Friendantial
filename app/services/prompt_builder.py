from typing import Any, Dict, List

from fastapi import Request

from app.schemas.models import RecoItem


def build_prompt(request: Request, template_name: str, **kwargs) -> str:
    """
    Jinja2 템플릿을 사용하여 프롬프트 문자열을 생성합니다.
    """
    template = request.app.state.jinja_env.get_template(template_name)
    return template.render(**kwargs)


def generate_news_analysis_xml(news_analysis: Dict[str, Any]) -> str:
    """
    뉴스 분석 결과를 XML 형식의 문자열로 변환합니다.
    """
    if not news_analysis or not news_analysis.get("details"):
        return "<summary>분석할 최신 뉴스가 없습니다.</summary>"

    news_items_xml = "".join(
        [
            f"<item label='{news['label']}'>{news['title']}</item>"
            for news in news_analysis["details"]
        ]
    )
    return f"""
<summary>{news_analysis['summary']}</summary>
<items>{news_items_xml}</items>
"""


def generate_stock_data_xml(candidates: List[RecoItem]) -> str:
    """
    추천 종목 리스트를 XML 형식의 문자열로 변환합니다.
    """
    stock_data_xml = ""
    for item in candidates:
        news_xml = ""
        if item.news_sentiment and item.news_sentiment.details:
            news_items_xml = "".join(
                [
                    f"<item label='{news_item.label}'>{news_item.title}</item>"
                    for news_item in item.news_sentiment.details
                ]
            )
            news_xml = f"<news>{news_items_xml}</news>"

        stock_data_xml += f"""
<stock code='{item.code}' name='{item.name}'>
<score>{item.score}</score>
<stars>{item.stars}</stars>
<reason>{item.reason}</reason>
<momentum m5='{item.momentum.get('m5', 0):.2%}' m20='{item.momentum.get('m20', 0):.2%}' m60='{item.momentum.get('m60', 0):.2%}' />
{news_xml}
</stock>"""
    return stock_data_xml
