from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from btc_tool.models import SpecialEvent, Trade


CONVERT_RE = re.compile(
    r"converted\s+([0-9.,]+)\s+([A-Z0-9]+)\s+to\s+([0-9.,]+)\s+([A-Z0-9]+)",
    re.IGNORECASE,
)


def _clean_money(value: str | None) -> float:
    if not value:
        return 0.0
    return float(value.replace("€", "").replace(",", "").strip())


def _clean_amount(value: str | None) -> float:
    if not value:
        return 0.0
    return abs(float(value.strip().replace(",", "")))


def _parse_timestamp(value: str) -> datetime:
    value = value.replace(" UTC", "").strip()
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _safe_text(value: str | None) -> str:
    return (value or "").strip()


def _parse_convert_from_notes(notes: str) -> tuple[float, str, float, str] | None:
    match = CONVERT_RE.search(notes)
    if not match:
        return None

    from_amount = float(match.group(1).replace(",", ""))
    from_asset = match.group(2).upper()
    to_amount = float(match.group(3).replace(",", ""))
    to_asset = match.group(4).upper()

    return from_amount, from_asset, to_amount, to_asset


def load_trades_from_csv(
    path: str | Path,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    trades: List[Trade] = []
    special_events: List[SpecialEvent] = []
    raw_rows: List[Dict] = []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("CSV file is empty.")

    header_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("ID,Timestamp,Transaction Type,Asset"):
            header_index = i
            break

        if stripped.startswith("Timestamp,Transaction Type,Asset"):
            header_index = i
            break

    if header_index is None:
        raise ValueError("Could not find a valid Coinbase CSV header.")

    reader = csv.DictReader(lines[header_index:])

    for row in reader:
        if not row:
            continue

        tx_type_raw = _safe_text(row.get("Transaction Type"))
        asset = _safe_text(row.get("Asset")).upper()
        timestamp_raw = _safe_text(row.get("Timestamp"))
        notes = _safe_text(row.get("Notes"))

        if not tx_type_raw or not timestamp_raw:
            continue

        tx_type = tx_type_raw.lower()
        date = _parse_timestamp(timestamp_raw)

        amount = _clean_amount(row.get("Quantity Transacted"))
        price = _clean_money(row.get("Price at Transaction"))
        fee = _clean_money(row.get("Fees and/or Spread"))
        subtotal = _clean_money(row.get("Subtotal"))
        total = _clean_money(row.get("Total (inclusive of fees and/or spread)"))

        raw_rows.append(
            {
                "date": date,
                "asset": asset,
                "transaction_type": tx_type,
                "amount": amount,
                "price": price,
                "fee": fee,
                "subtotal": subtotal,
                "total": total,
                "notes": notes,
                "source_row": row,
            }
        )

        if tx_type in {"buy", "advanced trade buy"}:
            trades.append(
                Trade(
                    date=date,
                    asset=asset,
                    type="buy",
                    amount=amount,
                    price=price,
                    fee=fee,
                )
            )
            continue

        if tx_type in {"sell", "advanced trade sell"}:
            trades.append(
                Trade(
                    date=date,
                    asset=asset,
                    type="sell",
                    amount=amount,
                    price=price,
                    fee=fee,
                )
            )
            continue

        if tx_type in {"staking income", "rewards income"}:
            trades.append(
                Trade(
                    date=date,
                    asset=asset,
                    type="buy",
                    amount=amount,
                    price=price,
                    fee=0.0,
                )
            )

            special_events.append(
                SpecialEvent(
                    date=date,
                    asset=asset,
                    event_type=tx_type,
                    amount=amount,
                    price=price,
                    fee=0.0,
                    notes=notes,
                )
            )
            continue

        if tx_type == "convert":
            parsed = _parse_convert_from_notes(notes)

            if parsed is None:
                special_events.append(
                    SpecialEvent(
                        date=date,
                        asset=asset or "UNKNOWN",
                        event_type=tx_type,
                        amount=amount,
                        price=price,
                        fee=fee,
                        notes=notes,
                    )
                )
                continue

            from_amount, from_asset, to_amount, to_asset = parsed

            sell_price = price
            if sell_price == 0.0 and from_amount > 0 and subtotal > 0:
                sell_price = subtotal / from_amount

            buy_price = price
            if buy_price == 0.0 and to_amount > 0 and subtotal > 0:
                buy_price = subtotal / to_amount

            trades.append(
                Trade(
                    date=date,
                    asset=from_asset,
                    type="sell",
                    amount=from_amount,
                    price=sell_price,
                    fee=fee,
                )
            )

            trades.append(
                Trade(
                    date=date,
                    asset=to_asset,
                    type="buy",
                    amount=to_amount,
                    price=buy_price,
                    fee=0.0,
                )
            )

            special_events.append(
                SpecialEvent(
                    date=date,
                    asset=f"{from_asset}->{to_asset}",
                    event_type="convert",
                    amount=from_amount,
                    price=sell_price,
                    fee=fee,
                    notes=notes,
                )
            )
            continue

        special_events.append(
            SpecialEvent(
                date=date,
                asset=asset or "UNKNOWN",
                event_type=tx_type,
                amount=amount,
                price=price,
                fee=fee,
                notes=notes,
            )
        )

    return trades, special_events, raw_rows
