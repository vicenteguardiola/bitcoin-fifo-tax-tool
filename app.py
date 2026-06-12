import argparse
from pathlib import Path

from btc_tool.engine.fifo import calculate_fifo
from btc_tool.engine.staking import (
    summarize_special_events,
    summarize_transaction_types,
)
from btc_tool.io.csv_loader import load_trades_from_csv
from btc_tool.io.price_loader import PriceLoader
from btc_tool.reporting.export_audit_csv import export_audit_csv
from btc_tool.reporting.export_open_lots_csv import export_open_lots_csv
from btc_tool.reporting.export_summary_txt import export_summary_txt
from btc_tool.reporting.tax_report import build_tax_report


def main():
    parser = argparse.ArgumentParser(description="Bitcoin FIFO Tax Tool")

    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        metavar="CSV",
        help=(
            "One or more exchange CSV files to process "
            "(Coinbase, Uphold, Revolut). "
            "Example: --files data/coinbase.csv data/uphold.csv"
        ),
    )

    parser.add_argument(
        "--prices",
        nargs="+",
        help="Price CSV files (CoinMarketCap format) for accurate pricing",
    )

    parser.add_argument(
        "--price-dir",
        help="Directory containing all price CSV files",
    )

    parser.add_argument(
        "--skip-uphold-in",
        action="store_true",
        help=(
            "Skip Uphold 'in' (deposit) transactions. Use this when you are also "
            "loading the source exchange CSV (e.g. Coinbase) to avoid counting the "
            "same crypto lot twice."
        ),
    )

    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help=(
            "Filter the tax report to a specific fiscal year (e.g. --year 2025). "
            "All data is still processed for correct FIFO inventory."
        ),
    )

    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Do not write output files",
    )

    args = parser.parse_args()

    # ── Load historical price data ───────────────────────────────────────────
    price_loader = None
    if args.price_dir or args.prices:
        price_loader = PriceLoader()

        if args.price_dir:
            print(f"Loading price data from directory: {args.price_dir}")
            price_loader.load_from_directory(args.price_dir)

        if args.prices:
            for price_file in args.prices:
                print(f"Loading price data from: {price_file}")
                price_loader.load_from_csv(price_file)

        print(f"Loaded prices for assets: {', '.join(price_loader.assets())}")
        for asset in price_loader.assets():
            start_date, end_date = price_loader.price_range(asset)
            print(f"  {asset}: {start_date} to {end_date}")
        print()

    # ── Load and merge all exchange CSVs ─────────────────────────────────────
    all_trades = []
    all_special_events = []
    all_raw_rows = []

    for csv_path in args.files:
        try:
            trades, special_events, raw_rows = load_trades_from_csv(
                csv_path,
                price_loader,
                skip_uphold_in=args.skip_uphold_in,
            )
        except FileNotFoundError:
            print(f"Error: file not found: {csv_path}")
            return
        except ValueError as e:
            print(f"Error loading {csv_path}: {e}")
            return

        raw_row_count = raw_rows if isinstance(raw_rows, int) else len(raw_rows)
        print(f"Loaded: {csv_path}")
        print(f"  Raw rows       : {raw_row_count}")
        print(f"  Buy/Sell trades: {len(trades)}")
        print(f"  Special events : {len(special_events)}")
        if trades:
            print(f"  First trade    : {trades[0]}")
        print()

        all_trades.extend(trades)
        all_special_events.extend(special_events)
        if isinstance(raw_rows, list):
            all_raw_rows.extend(raw_rows)

    # Sort all trades chronologically before FIFO
    all_trades.sort(key=lambda t: t.date)

    total_raw_count = len(all_raw_rows)
    print(
        f"Combined: {len(all_trades)} trades from "
        f"{len(args.files)} file(s) — ready for FIFO\n"
    )

    # ── FIFO calculation (always uses ALL trades for correct inventory) ───────
    _, all_matches, open_lots = calculate_fifo(all_trades)

    # ── Filter matches to report year if requested ────────────────────────────
    report_year = args.year
    if report_year:
        matches = [m for m in all_matches if m.sell_date.year == report_year]
        year_label = str(report_year)
    else:
        matches = all_matches
        year_label = "all years"

    tax_report = build_tax_report(matches)
    special_summary = summarize_special_events(all_special_events)
    tx_type_summary = summarize_transaction_types(all_raw_rows) if all_raw_rows else {}

    total_profit = sum(m.profit for m in matches)
    taxable_profit = sum(m.profit for m in matches if m.tax_status == "taxable")
    tax_free_profit = sum(m.profit for m in matches if m.tax_status == "tax_free")

    # ── Report ───────────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 50)
    lines.append("BITCOIN TOOL - FIFO REPORT")
    if report_year:
        lines.append(f"Fiscal year: {report_year}")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"CSV Rows Total: {total_raw_count}")
    lines.append(f"Processed Buy/Sell Trades: {len(all_trades)}")
    lines.append(f"Special Events Found: {len(all_special_events)}")
    lines.append(f"Matches in report ({year_label}): {len(matches)}")
    lines.append("")
    lines.append("TRANSACTION TYPES FOUND")
    lines.append("-" * 50)

    if tx_type_summary:
        for tx_type in sorted(tx_type_summary.keys()):
            lines.append(f"{tx_type} | Count: {tx_type_summary[tx_type]}")
    else:
        lines.append("No transaction type summary available.")

    lines.append("")
    lines.append(f"Total Profit ({year_label}): {total_profit:.2f}")
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
    lines.append(f"MATCHES ({year_label})")
    lines.append("-" * 50)

    if matches:
        for match in matches:
            lines.append(
                f"Sell Date: {match.sell_date.date()} | "
                f"Asset: {match.asset} | "
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

        year_suffix = f"_{report_year}" if report_year else ""

        summary_file = export_summary_txt(
            total_profit=total_profit,
            matches=matches,
            open_lots=open_lots,
            out_path=output_dir / f"summary{year_suffix}.txt",
        )
        audit_file = export_audit_csv(
            matches, output_dir / f"audit{year_suffix}.csv"
        )
        open_lots_file = export_open_lots_csv(
            open_lots, output_dir / "open_lots.csv"
        )

        print(f"Audit CSV saved to: {audit_file}")
        print(f"Open Lots CSV saved to: {open_lots_file}")
        print(f"Report saved to: {summary_file}")


if __name__ == "__main__":
    main()
