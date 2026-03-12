from datetime import datetime
from dateutil.relativedelta import relativedelta


def holding_days(buy_date: datetime, sell_date: datetime) -> int:
    return (sell_date - buy_date).days


def held_more_than_one_year(buy_date: datetime, sell_date: datetime) -> bool:
    return sell_date > buy_date + relativedelta(years=1)


def tax_status_de(buy_date: datetime, sell_date: datetime) -> str:
    if held_more_than_one_year(buy_date, sell_date):
        return "tax_free"
    return "taxable"