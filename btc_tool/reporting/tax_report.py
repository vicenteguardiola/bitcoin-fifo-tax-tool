from __future__ import annotations

from collections import defaultdict

from btc_tool.models import MatchRow


def build_tax_report(matches: list[MatchRow]) -> dict[int, dict[str, float]]:
    report = defaultdict(lambda: {"taxable_profit": 0.0, "tax_free_profit": 0.0})

    for match in matches:
        year = match.sell_date.year

        if match.tax_status == "taxable":
            report[year]["taxable_profit"] += match.profit
        elif match.tax_status == "tax_free":
            report[year]["tax_free_profit"] += match.profit

    return dict(report)