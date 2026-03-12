from __future__ import annotations

from pathlib import Path
from typing import List

from btc_tool.models import MatchRow


def export_summary_txt(
    total_profit: float,
    matches: List[MatchRow],
    open_lots: list[dict],
    out_path: str = "outputs/summary.txt",
) -> str:
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    taxable_profit = sum(m.profit for m in matches if m.tax_status == "taxable")
    tax_free_profit = sum(m.profit for m in matches if m.tax_status == "tax_free")

    lines = []
    lines.append("BITCOIN TOOL - FIFO REPORT")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Total Profit: {total_profit:.2f}")
    lines.append(f"Taxable Profit: {taxable_profit:.2f}")
    lines.append(f"Tax Free Profit: {tax_free_profit:.2f}")
    lines.append("")
    lines.append("MATCHES")
    lines.append("-" * 50)

    if matches:
        for m in matches:
            lines.append(
                f"Sell Date: {m.sell_date.date()} | "
                f"Sold: {m.sell_amount:.8f} | "
                f"Buy Price: {m.buy_price:.2f} | "
                f"Sell Price: {m.sell_price:.2f} | "
                f"Profit: {m.profit:.2f} | "
                f"Tax: {m.tax_status}"
            )
    else:
        lines.append("No matches.")

    lines.append("")
    lines.append("OPEN LOTS")
    lines.append("-" * 50)

    if open_lots:
        for lot in open_lots:
            lines.append(
                f"Date: {lot['date'].date()} | "
                f"Amount: {lot['amount']:.8f} | "
                f"Price: {lot['price']:.2f}"
            )
    else:
        lines.append("No open lots.")

    text = "\n".join(lines)
    out_file.write_text(text, encoding="utf-8")

    return str(out_file)