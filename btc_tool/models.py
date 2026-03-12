from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Trade:
    date: datetime
    asset: str
    type: str
    amount: float
    price: float
    fee: float = 0.0


@dataclass(frozen=True)
class SpecialEvent:
    date: datetime
    asset: str
    event_type: str
    amount: float
    price: float
    fee: float = 0.0
    notes: str = ""


@dataclass
class MatchRow:
    asset: str
    sell_date: datetime
    sell_amount: float
    sell_price: float
    sell_fee_part: float
    buy_date: datetime
    buy_amount: float
    buy_price: float
    buy_fee_part: float
    cost_basis: float
    proceeds: float
    profit: float
    holding_days: int
    held_more_than_1y: bool
    tax_status: str