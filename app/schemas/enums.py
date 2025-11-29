# app/schemas/enums.py

from enum import Enum


class PersonaEnum(str, Enum):
    FRIEND = "friend"
    ANALYST = "analyst"


class StrategyEnum(str, Enum):
    DAY_TRADER = "day_trader"
    LONG_TERM = "long_term_trader"
