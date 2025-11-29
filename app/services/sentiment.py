# app/services/sentiment.py

import asyncio
import logging
import math
import re
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from typing import List
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

from ..config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NEWS_MAX,
    SENTIMENT_BATCH_SIZE,
    SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL,
    SENTIMENT_CONFIDENCE_THRESHOLD_STRONG,
    SENTIMENT_MODEL_ID,
    SENTIMENT_NEWS_WEIGHT_DECAY_RATE,
)

# oid: 네이버 뉴스 검색 결과에서 언론사를 의미하는 link URL의 쿼리 파라미터
# 주요 언론사의 oid를 매핑하여 발행처를 식별하는 데 사용
NAVER_NEWS_OIDS = dict(
    (
        ("001", "연합뉴스"),
        ("003", "뉴시스"),
        ("005", "국민일보"),
        ("008", "머니투데이"),
        ("011", "서울경제"),
        ("014", "파이낸셜뉴스"),
        ("015", "한국경제"),
        ("016", "헤럴드경제"),
        ("018", "이데일리"),
        ("020", "동아일보"),
        ("021", "문화일보"),
        ("022", "세계일보"),
        ("023", "조선일보"),
        ("025", "중앙일보"),
        ("028", "한겨레"),
        ("030", "전자신문"),
        ("031", "아이뉴스24"),
        ("032", "경향신문"),
        ("055", "SBS"),
        ("056", "KBS"),
        ("057", "MBN"),
        ("081", "서울신문"),
        ("082", "한국일보"),
        ("214", "MBC"),
        ("277", "아시아경제"),
        ("374", "SBS Biz"),
        ("421", "뉴스1"),
        ("422", "YTN"),
        ("448", "TV조선"),
        ("449", "채널A"),
    )
)


@asynccontextmanager
async def sentiment_lifespan(app):
    """FastAPI lifespan 이벤트 핸들러로, 애플리케이션 시작 시 감성 분석 모델을 비동기적으로 로드합니다."""
    logging.info("Sentiment pipeline 초기화 작업을 시작합니다...")

    # 1. 일단 빈 상태로 시작 (서버 부팅 차단 방지)
    app.state.sentiment_pipe = None

    # 2. 실제 로딩을 수행할 내부 비동기 함수 정의
    async def load_model_background():
        try:
            # CPU를 많이 쓰는 작업을 별도 스레드에서 실행하여 이벤트 루프 차단 방지
            logging.info("감성 분석 모델 로딩 중...")

            # 토크나이저와 모델 로드 (동기 함수이므로 to_thread 사용)
            tok, mdl = await asyncio.to_thread(
                lambda: (
                    AutoTokenizer.from_pretrained(SENTIMENT_MODEL_ID),
                    AutoModelForSequenceClassification.from_pretrained(
                        SENTIMENT_MODEL_ID, use_safetensors=True
                    ),
                )
            )

            # 파이프라인 생성
            pipe = await asyncio.to_thread(
                lambda: pipeline(
                    "sentiment-analysis", model=mdl, tokenizer=tok, device=-1
                )
            )
            # app.state에 직접 파이프라인 설정
            app.state.analysis_service.sentiment_pipe = pipe
            app.state.sentiment_pipe = pipe
            logging.info(
                f"Sentiment pipeline 준비 완료 되었습니다.: {SENTIMENT_MODEL_ID}"
            )

        except Exception as e:
            logging.error(f"Sentiment pipeline 초기화 중 오류가 발생하였습니다.: {e}")

    # 3. 백그라운드 태스크로 실행! (기다리지 않고 넘어감)
    asyncio.create_task(load_model_background())

    yield

    logging.info("Sentiment pipeline을 정리합니다.")
    app.state.analysis_service.sentiment_pipe = None
    app.state.sentiment_pipe = None


async def fetch_news_titles(
    client: httpx.AsyncClient, query: str, limit: int = NEWS_MAX
) -> List[str]:
    if limit <= 0:
        return []

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logging.error(
            "네이버 뉴스 API credentials(NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)가 설정되지 않았습니다."
        )
        return []

    # 이슈: "두산"과 같은 종목명만으로 검색하면 야구 등 관련 없는 뉴스가 포함됨
    # 해결: "증권", "경제"와 같은 키워드를 추가하여 금융/경제 관련 뉴스의 우선순위를 높임
    search_query = f"{query} 증권 경제"
    encoded_query = quote_plus(search_query)
    url = f"https://openapi.naver.com/v1/search/news.xml?query={encoded_query}&display={limit}&start=1&sort=sim"  # sim: 정확도순
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    try:
        r = await client.get(url, headers=headers, timeout=10.0)
        if r.status_code != 200 or not r.text:
            return []
        titles: List[str] = []
        root = ET.fromstring(r.text)
        for item in root.findall("./channel/item"):
            publisher = "출처 미상"
            # 1. 네이버 뉴스 링크(oid 포함)를 우선적으로 파싱
            link_node = item.find("link")
            if link_node is not None and link_node.text:
                try:
                    parsed_url = urlparse(link_node.text)
                    if parsed_url.hostname and "news.naver.com" in parsed_url.hostname:
                        query_params = parse_qs(parsed_url.query)
                        oid = query_params.get("oid", [None])[0]
                        if oid and oid in NAVER_NEWS_OIDS:
                            publisher = NAVER_NEWS_OIDS.get(oid, f"OID:{oid}")
                except Exception:
                    pass  # 파싱 실패 시 다음 단계

            # 2. 네이버 뉴스 링크에서 언론사를 찾지 못한 경우, 원문 링크의 도메인을 사용
            if publisher == "출처 미상":
                original_link_node = item.find("originallink")
                if original_link_node is not None and original_link_node.text:
                    try:
                        hostname = urlparse(original_link_node.text).hostname
                        if hostname:
                            # 'm.hankooki.com' -> 'hankooki'
                            publisher = re.sub(
                                r"^(www|m)\.|\.(com|co\.kr|kr|net|org)$", "", hostname
                            ).strip()
                            publisher = (
                                publisher or "출처 미상"
                            )  # 정제 후 빈 문자열이 되면 '출처 미상'
                    except Exception:
                        pass

            tnode = item.find("title")
            if tnode is not None and tnode.text and (t := tnode.text.strip()):
                # 뉴스 제목에서 <b> 같은 HTML 태그와 특수문자를 제거
                clean_title = re.sub(r"<[/]?b>|&[a-z]+;", "", t).strip()
                titles.append(f"[{publisher}] {clean_title}")
                if len(titles) >= limit:
                    break
        return titles
    except Exception as e:
        logging.warning(f"뉴스 수집 중 오류가 발생하였습니다. (종목: {query}): {e}")
        return []


def _get_sentiment_details_from_prediction(
    label: str, confidence: float, id2label: dict
) -> tuple[str, int]:
    """모델 예측 결과를 바탕으로 표시용 레이블과 감성 값(-1,0,1)을 반환합니다."""
    if (
        confidence < SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL
    ):  # 신뢰도가 낮으면 중립으로 처리
        return "중립", 0

    is_strong = confidence >= SENTIMENT_CONFIDENCE_THRESHOLD_STRONG

    try:
        # 'LABEL_2'와 같은 형식을 처리하기 위해 숫자 인덱스를 추출
        label_index = int(label.split("_")[-1])
    except ValueError:
        # 'positive'와 같은 문자열 레이블인 경우, 레이블 자체를 사용
        label_index = label
    semantic_label = id2label.get(label_index, str(label)).lower()

    # KR-FinBERT: 2=긍정, 1=중립, 0=부정
    positive_labels = ["2", "positive"]
    negative_labels = ["0", "negative"]

    if semantic_label in positive_labels:
        display_label = "강력한 호재" if is_strong else "호재"
        return display_label, 1
    if semantic_label in negative_labels:
        display_label = "강력한 악재" if is_strong else "악재"
        return display_label, -1

    # '1', 'neutral' 또는 예상치 못한 레이블은 모두 중립으로 처리
    return "중립", 0


def analyze_news_sentiment(pipe: pipeline, headlines: List[str]) -> dict:
    """주어진 뉴스 제목 리스트에 대해 감성 분석을 수행하고, 종합 점수와 개별 분석 결과를 반환합니다."""
    if not headlines:
        return {
            "enabled": False,
            "summary": "no headlines",
            "details": [],
        }
    if not pipe:
        return {
            "enabled": False,
            "summary": "model not available",
            "details": [],
        }

    details = []
    score_acc = 0.0
    id2label = pipe.model.config.id2label
    preds = pipe(
        headlines, batch_size=SENTIMENT_BATCH_SIZE, truncation=True, max_length=512
    )

    for i, (title, pred) in enumerate(zip(headlines, preds)):
        label = pred.get("label", "neutral")
        confidence = float(pred.get("score", 0.0))

        display_label, sentiment_value = _get_sentiment_details_from_prediction(
            label, confidence, id2label
        )

        # 최신 뉴스에 더 높은 가중치를 부여하기 위해 지수 감쇠(exponential decay)를 적용합니다.
        weight = math.exp(-SENTIMENT_NEWS_WEIGHT_DECAY_RATE * i)
        score_acc += sentiment_value * weight

        details.append(
            {"title": title, "label": display_label, "confidence": round(confidence, 3)}
        )

    summary = f"최근 뉴스 {len(details)}건 분석 완료하였습니다."
    return {
        "enabled": True,
        "summary": summary,
        "details": details,
    }
