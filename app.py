import argparse
from pathlib import Path

from btc_tool.engine.fifo import calculate_fifo
from btc_tool.engine.staking import (
    summarize_special_events,
    summarize_transaction_types,
)
from btc_tool.io.csv_loader import load_trades_from_csv
from btc_tool.reporting.export_audit_csv import export_audit_csv
from btc_tool.reporting.export_open_lots_csv import export_open_lots_csv
from btc_tool.reporting.export_summary_txt import export_summary_txt
from btc_tool.reporting.tax_report import build_tax_report


def main():
    parser = argparse.ArgumentParser(description="Bitcoin FIFO Tax Tool")

    parser.add_argument(
        "--file",
        default="data/coinbase.csv",
        help="Path to Coinbase CSV file",
    )

    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Do not write output files",
    )

    args = parser.parse_args()
    csv_path = args.file

    try:
        trades, special_events, raw_rows = load_trades_from_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: file not found: {csv_path}")
        return
    except ValueError as e:
        print(f"Error: {e}")
        return

    raw_row_count = raw_rows if isinstance(raw_rows, int) else len(raw_rows)

    print(f"Loaded trades from: {csv_path}")
    print(f"Raw rows: {raw_row_count}")
    print(f"Parsed Buy/Sell trades: {len(trades)}")
    print(f"Special events found: {len(special_events)}")
    if trades:
        print(f"First parsed trade: {trades[0]}")
    else:
        print("No parsed trades found.")
    print()

    total_profit, matches, open_lots = calculate_fifo(trades)
    tax_report = build_tax_report(matches)
    special_summary = summarize_special_events(special_events)

    if isinstance(raw_rows, int):
        tx_type_summary = {}
    else:
        tx_type_summary = summarize_transaction_types(raw_rows)

    taxable_profit = sum(m.profit for m in matches if m.tax_status == "taxable")
    tax_free_profit = sum(m.profit for m in matches if m.tax_status == "tax_free")

    lines = []
    lines.append("=" * 50)
    lines.append("BITCOIN TOOL - FIFO REPORT")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"CSV Rows Total: {raw_row_count}")
    lines.append(f"Processed Buy/Sell Trades: {len(trades)}")
    lines.append(f"Special Events Found: {len(special_events)}")
    lines.append("")
    lines.append("TRANSACTION TYPES FOUND")
    lines.append("-" * 50)

    if tx_type_summary:
        for tx_type in sorted(tx_type_summary.keys()):
            lines.append(f"{tx_type} | Count: {tx_type_summary[tx_type]}")
    else:
        lines.append("No transaction type summary available.")

    lines.append("")
    lines.append(f"Total Profit: {total_profit:.2f}")
    lines.append(f"Taxable Profit: {taxable_profit:.2f}")
    lines.append(f"Tax Free Profit: {tax_free_profit:.2f}")
    lines.append("")
    lines.append("TAX REPORT BY YEAR")
    lines.append("-" * 50)

    if tax_report:
        for year in sorted(tax_report.keys()):
            lines.append(
                f"{year} | "
                f"Taxable Profit: {tax_report[year]['taxable_profit']:.2f} | "
                f"Tax Free Profit: {tax_report[year]['tax_free_profit']:.2f}"
            )
    else:
        lines.append("No tax report data.")

    lines.append("")
    lines.append("SPECIAL EVENTS")
    lines.append("-" * 50)

    if special_summary:
        for event_type in sorted(special_summary.keys()):
            lines.append(event_type.upper())
            for asset in sorted(special_summary[event_type].keys()):
                item = special_summary[event_type][asset]
                lines.append(
                    f"  {asset} | Count: {int(item['count'])} | Amount: {item['amount']:.8f}"
                )
    else:
        lines.append("No special events.")

    lines.append("")
    lines.append("MATCHES")
    lines.append("-" * 50)

    if matches:
        for match in matches:
            lines.append(
                f"Sell Date: {match.sell_date.date()} | "
                f"Sold: {match.sell_amount:.8f} | "
                f"Buy Price: {match.buy_price:.2f} | "
                f"Sell Price: {match.sell_price:.2f} | "
                f"Profit: {match.profit:.2f} | "
                f"Tax: {match.tax_status} | "
                f">1Y: {match.held_more_than_1y}"
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
                f"Asset: {lot['asset']} | "
                f"Amount: {lot['amount']:.8f} | "
                f"Price: {lot['price']:.2f}"
            )
    else:
        lines.append("No open lots.")

    lines.append("")
    lines.append("=" * 50)

    report_text = "\n".join(lines)
    print(report_text)

    if not args.no_export:
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)

        summary_file = export_summary_txt(
            total_profit=total_profit,
            matches=matches,
            open_lots=open_lots,
            out_path=output_dir / "summary.txt",
        )
        audit_file = export_audit_csv(matches, output_dir / "audit.csv")
        open_lots_file = export_open_lots_csv(open_lots, output_dir / "open_lots.csv")

        print(f"Audit CSV saved to: {audit_file}")
        print(f"Open Lots CSV saved to: {open_lots_file}")
        print(f"Report saved to: {summary_file}")


if __name__ == "__main__":
    main()