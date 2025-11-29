# app/core/presentation.py

from ..schemas.models import RecoItem, StockScore


def generate_friendly_reason(stock_score: StockScore) -> str:
    """수치 데이터를 바탕으로 친절한 설명 문구를 생성합니다."""
    mom = stock_score.momentum
    m5 = mom.get("m5", 0.0)
    rsi = mom.get("rsi", 50.0)

    parts = []

    # 1. 모멘텀(추세) 평가
    if m5 > 0.15:
        parts.append("최근 주가가 급등하여 기세가 아주 강하며,")
    elif m5 > 0.05:
        parts.append("탄탄한 상승 추세를 이어가고 있으며,")
    elif m5 > 0:
        parts.append("완만한 상승 흐름을 보이는 가운데,")
    else:
        parts.append("단기적으로 조정을 받고 있으나,")

    # 2. RSI(과열/침체) 평가
    if rsi >= 80:
        parts.append(
            f"RSI({rsi:.0f})가 초과열권이라 '매도' 압력이 커질 수 있어 주의가 필요합니다."
        )
    elif rsi >= 70:
        parts.append(f"RSI({rsi:.0f})가 과열권에 진입해 잠시 쉬어갈 수 있습니다.")
    elif rsi <= 30:
        parts.append(
            f"RSI({rsi:.0f})가 침체권이라 기술적 '반등'이 기대되는 자리입니다."
        )
    else:
        parts.append(f"과열되지 않은 건전한 수급(RSI {rsi:.0f})을 유지하고 있습니다.")

    return " ".join(parts)


def calculate_stock_stars(item: RecoItem, market_regime: str) -> int:
    """종합 점수와 리스크 요인을 고려하여 별점을 부여합니다."""
    score = item.score
    rsi = item.momentum.get("rsi", 50.0)

    thresholds = {
        "BULL": [60, 70, 80, 90],
        "NEUTRAL": [65, 75, 85, 95],
        "BEAR": [70, 80, 90, 97],
    }.get(market_regime, [65, 75, 85, 95])

    stars = 1
    if score >= thresholds[3]:
        stars = 5
    elif score >= thresholds[2]:
        stars = 4
    elif score >= thresholds[1]:
        stars = 3
    elif score >= thresholds[0]:
        stars = 2

    # 리스크 필터 (RSI, 뉴스 악재 등)
    if rsi >= 80:
        stars = min(stars, 4)
    if rsi >= 90:
        stars = min(stars, 3)
    if item.news_sentiment and "강력한 악재" in str(item.news_sentiment):
        stars = min(stars, 3)

    return stars


def scale_to_100(
    score: float, min_raw: float, max_raw: float, market_regime: str
) -> int:
    """원본 점수를 0~100점으로 변환하며, 시장 상황에 따라 Cap을 적용합니다."""
    score_cap = 100
    if market_regime == "BEAR":
        score_cap = 80
    if max_raw < 0.0:
        score_cap = min(score_cap, 50)

    if max_raw == min_raw:
        return 50

    normalized = (score - min_raw) / (max_raw - min_raw)

    if normalized < 0.2:
        scaled = normalized / 0.2 * 60
    else:
        scaled = 60 + (normalized - 0.2) / 0.8 * 40

    final_score = scaled * (score_cap / 100.0)
    return int(final_score)


def generate_ma_comment(price: float, ma5: float, ma20: float, ma60: float) -> str:
    """이동평균선 배열 상태와 주가 위치를 분석하여 코멘트를 생성합니다."""
    parts = []

    # 1. 정배열/역배열 판단 (장기 추세)
    if ma5 > ma20 > ma60:
        parts.append(
            "이동평균선이 정배열(단기>중기>장기)을 이루어 '강력한 상승 추세'를 보이고 있습니다."
        )
    elif ma5 < ma20 < ma60:
        parts.append("이동평균선이 역배열 상태라 '하락 추세'가 지속되고 있습니다.")

    # 2. 현재 주가와 이평선 관계 (단기 탄력)
    if price > ma5:
        parts.append("현재 주가가 5일선 위에 있어 단기 탄력이 좋습니다.")
    elif price < ma5:
        parts.append("주가가 5일선 아래로 내려와 단기 조정을 받고 있습니다.")

    # 3. 골든크로스/데드크로스 징후 (예정)
    # (수치 차이가 1% 이내일 때 등 정교한 로직 추가 가능)

    # 4. 지지/저항 (가장 가까운 이평선 찾기)
    # 예: 주가가 MA20 근처에 있으면 "20일선 지지 여부가 중요합니다."

    if not parts:
        parts.append("이동평균선이 혼조세를 보이며 뚜렷한 방향성을 탐색 중입니다.")

    return " ".join(parts)
