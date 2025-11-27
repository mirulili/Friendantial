from enum import Enum


class PersonaEnum(str, Enum):
    FRIEND = "friend"
    ANALYST = "analyst"


class StrategyEnum(str, Enum):
    DEFAULT = "default"
    DAY_TRADER = "day_trader"
    LONG_TERM = "long_term"
