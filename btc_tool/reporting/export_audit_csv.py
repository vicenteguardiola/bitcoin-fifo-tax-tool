from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from btc_tool.models import MatchRow


def _fmt_amount(value: float) -> str:
    return f"{value:.8f}"


def _fmt_money(value: float) -> str:
    return f"{value:.2f}"


def _fmt_bool(value: bool) -> str:
    return "true" if value else "false"


def export_audit_csv(matches: list[MatchRow], out_path: str = "outputs/audit.csv") -> str:
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "asset",
        "sell_date",
        "sell_amount",
        "sell_price",
        "sell_fee_part",
        "buy_date",
        "buy_amount",
        "buy_price",
        "buy_fee_part",
        "cost_basis",
        "proceeds",
        "profit",
        "holding_days",
        "held_more_than_1y",
        "tax_status",
    ]

    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for match in matches:
            row = asdict(match)

            writer.writerow(
                {
                    "asset": row["asset"],
                    "sell_date": row["sell_date"],
                    "sell_amount": _fmt_amount(row["sell_amount"]),
                    "sell_price": _fmt_money(row["sell_price"]),
                    "sell_fee_part": _fmt_money(row["sell_fee_part"]),
                    "buy_date": row["buy_date"],
                    "buy_amount": _fmt_amount(row["buy_amount"]),
                    "buy_price": _fmt_money(row["buy_price"]),
                    "buy_fee_part": _fmt_money(row["buy_fee_part"]),
                    "cost_basis": _fmt_money(row["cost_basis"]),
                    "proceeds": _fmt_money(row["proceeds"]),
                    "profit": _fmt_money(row["profit"]),
                    "holding_days": row["holding_days"],
                    "held_more_than_1y": _fmt_bool(row["held_more_than_1y"]),
                    "tax_status": row["tax_status"],
                }
            )

    return str(out_file)