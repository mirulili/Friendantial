from abc import ABC, abstractmethod
from typing import List, Tuple

import pandas as pd

from ..config import (
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    RSI_STRONG_OVERBOUGHT,
    STRATEGY_CONFIG,
)


class BaseStrategy(ABC):
    """
    주식 채점 전략을 위한 추상 기본 클래스입니다.
    각 전략은 RSI 보너스, MA 페널티, 경고 메시지 생성 로직을 구현해야 합니다.
    """

    def __init__(self, strategy_name: str = "default"):
        self.config = STRATEGY_CONFIG.get(strategy_name, STRATEGY_CONFIG["default"])

    @property
    def mom_weights(self) -> Tuple[float, float, float]:
        return self.config["mom_weights"]

    @property
    def vol_penalty_weight(self) -> float:
        return self.config["vol_penalty_weight"]

    @property
    def news_impact_factor(self) -> float:
        return self.config["news_impact_factor"]

    @property
    @abstractmethod
    def description(self) -> str:
        """전략에 대한 설명(LLM 프롬프트용)을 반환합니다."""
        pass

    @abstractmethod
    def calculate_rsi_bonus(self, rsi: float) -> float:
        """RSI 값에 따른 보너스 점수를 계산합니다."""
        pass

    @abstractmethod
    def check_ma_penalty(
        self, last_close: float, prev_data: pd.Series
    ) -> Tuple[float, List[str]]:
        """이동평균선 이탈 여부를 확인하여 페널티 점수와 경고 메시지를 반환합니다."""
        pass


class DayTraderStrategy(BaseStrategy):
    """
    단기 트레이더 전략:
    - 과매도 구간(RSI < 30)에서의 반등을 노립니다.
    - 5일 이동평균선 이탈 시 페널티를 부여합니다.
    """

    def __init__(self):
        super().__init__("day_trader")

    @property
    def description(self) -> str:
        return (
            "<perspective>단기 트레이더 관점: '5일선 이탈', '거래량 급등' 등 "
            "단기 신호와 최신 뉴스 위주 분석.</perspective>"
        )

    def calculate_rsi_bonus(self, rsi: float) -> float:
        if rsi < RSI_OVERSOLD:
            return 2.0  # 과매도 구간: 강력한 매수 신호
        elif rsi > RSI_OVERBOUGHT:
            return -1.0  # 과매수 구간: 주의
        return 0.0

    def check_ma_penalty(
        self, last_close: float, prev_data: pd.Series
    ) -> Tuple[float, List[str]]:
        warnings = []
        penalty = 0.0
        if last_close < prev_data.get("ma5", float("inf")):
            penalty = 0.5
            warnings.append("5일선 이탈")
        return penalty, warnings


class LongTermStrategy(BaseStrategy):
    """
    장기 투자 전략:
    - 극단적인 RSI 수치를 피하고 안정적인 구간을 선호합니다.
    - 60일 이동평균선(장기 추세) 훼손 시 큰 페널티를 부여합니다.
    """

    def __init__(self):
        super().__init__("long_term")

    @property
    def description(self) -> str:
        return (
            "<perspective>장기 투자자 관점: 장기 모멘텀(m60), '장기 추세' 및 "
            "펀더멘털 안정성 위주 분석.</perspective>"
        )

    def calculate_rsi_bonus(self, rsi: float) -> float:
        if rsi < RSI_OVERSOLD or rsi > RSI_OVERBOUGHT:
            return -0.5  # 극단적인 지표는 장기 투자에 불안 요소
        return 0.0

    def check_ma_penalty(
        self, last_close: float, prev_data: pd.Series
    ) -> Tuple[float, List[str]]:
        warnings = []
        penalty = 0.0
        if last_close < prev_data.get("ma60", float("inf")):
            penalty = 1.0
            warnings.append("장기 추세 훼손")
        return penalty, warnings


class DefaultStrategy(BaseStrategy):
    """
    기본 전략:
    - 일반적인 RSI 과매도/과열 기준을 적용합니다.
    - 별도의 이동평균선 페널티는 없습니다.
    """

    def __init__(self):
        super().__init__("default")

    @property
    def description(self) -> str:
        return (
            "<perspective>일반 투자자 관점: 균형 잡힌 시각으로 "
            "모멘텀과 리스크를 종합적으로 분석.</perspective>"
        )

    def calculate_rsi_bonus(self, rsi: float) -> float:
        if rsi < RSI_OVERSOLD:
            return 0.5  # 저점 매수 기회
        elif rsi > RSI_STRONG_OVERBOUGHT:
            return -0.5  # 과열
        return 0.0

    def check_ma_penalty(
        self, last_close: float, prev_data: pd.Series
    ) -> Tuple[float, List[str]]:
        return 0.0, []


def get_strategy(strategy_name: str) -> BaseStrategy:
    """전략 이름에 해당하는 전략 인스턴스를 반환하는 팩토리 함수입니다."""
    strategies = {
        "day_trader": DayTraderStrategy,
        "long_term": LongTermStrategy,
    }
    return strategies.get(strategy_name, DefaultStrategy)()
