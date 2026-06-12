from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from btc_tool.models import SpecialEvent, Trade
from btc_tool.io.price_loader import PriceLoader


CONVERT_RE = re.compile(
    r"converted\s+([0-9.,]+)\s+([A-Z0-9]+)\s+to\s+([0-9.,]+)\s+([A-Z0-9]+)",
    re.IGNORECASE,
)

FIAT_CURRENCIES = {
    "EUR", "USD", "GBP", "CHF", "JPY", "AUD", "CAD",
    "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON",
}


def _is_fiat(asset: str) -> bool:
    return asset.upper() in FIAT_CURRENCIES


def _to_utc_naive(dt: datetime) -> datetime:
    """Convert any datetime to UTC offset-naive. Required to mix Coinbase and Uphold dates."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


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


def detect_exchange_format(lines: List[str]) -> str:
    for line in lines[:50]:
        stripped = line.strip()
        if stripped.startswith("ID,Timestamp,Transaction Type,Asset"):
            return "coinbase"
        if stripped.startswith("Timestamp,Transaction Type,Asset"):
            return "coinbase"
        if "Date" in stripped and "Destination" in stripped and "Origin" in stripped:
            return "uphold"
        if stripped.startswith("Completed Date,Description,Paid Out,Paid In"):
            return "revolut"
    raise ValueError("Could not detect CSV format. Supported formats: Coinbase, Uphold, Revolut")


def load_trades_from_csv(
    path: str | Path,
    price_loader: Optional[PriceLoader] = None,
    skip_uphold_in: bool = False,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()
    if not lines:
        raise ValueError("CSV file is empty.")
    exchange = detect_exchange_format(lines)
    if exchange == "coinbase":
        return _load_coinbase_csv(lines, price_loader)
    elif exchange == "uphold":
        return _load_uphold_csv(lines, price_loader, skip_uphold_in=skip_uphold_in)
    elif exchange == "revolut":
        return _load_revolut_csv(lines, price_loader)
    else:
        raise ValueError(f"Unknown exchange format: {exchange}")


def _load_coinbase_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    trades: List[Trade] = []
    special_events: List[SpecialEvent] = []
    raw_rows: List[Dict] = []

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

        # Preserve raw quantity to detect sign (Convert exports two rows: negative=source, positive=dest)
        quantity_raw = _safe_text(row.get("Quantity Transacted"))
        is_negative = quantity_raw.startswith("-")
        amount = _clean_amount(quantity_raw)

        price = _clean_money(row.get("Price at Transaction"))
        fee = _clean_money(row.get("Fees and/or Spread"))
        subtotal = _clean_money(row.get("Subtotal"))
        total = _clean_money(row.get("Total (inclusive of fees and/or spread)"))

        raw_rows.append({
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
            "exchange": "Coinbase",
        })

        if tx_type in {"buy", "advanced trade buy"}:
            trades.append(Trade(date=date, asset=asset, type="buy", amount=amount, price=price, fee=fee))
            continue

        if tx_type in {"sell", "advanced trade sell"}:
            trades.append(Trade(date=date, asset=asset, type="sell", amount=amount, price=price, fee=fee))
            continue

        if tx_type in {"staking income", "rewards income"}:
            trades.append(Trade(date=date, asset=asset, type="buy", amount=amount, price=price, fee=0.0))
            special_events.append(SpecialEvent(date=date, asset=asset, event_type=tx_type, amount=amount, price=price, fee=0.0, notes=notes))
            continue

        if tx_type == "convert":
            # Coinbase exports Convert as TWO rows:
            #   negative quantity = source asset  → skip, info is redundant
            #   positive quantity = dest asset    → process the full SELL+BUY pair
            if is_negative:
                special_events.append(SpecialEvent(
                    date=date, asset=asset or "UNKNOWN",
                    event_type="convert_source_row", amount=amount,
                    price=price, fee=fee, notes=notes,
                ))
                continue

            parsed = _parse_convert_from_notes(notes)
            if parsed is None:
                special_events.append(SpecialEvent(date=date, asset=asset or "UNKNOWN", event_type=tx_type, amount=amount, price=price, fee=fee, notes=notes))
                continue

            from_amount, from_asset, to_amount, to_asset = parsed

            sell_price = price
            if sell_price == 0.0 and from_amount > 0 and subtotal > 0:
                sell_price = subtotal / from_amount

            buy_price = price
            if buy_price == 0.0 and to_amount > 0 and subtotal > 0:
                buy_price = subtotal / to_amount

            trades.append(Trade(date=date, asset=from_asset, type="sell", amount=from_amount, price=sell_price, fee=fee))
            trades.append(Trade(date=date, asset=to_asset, type="buy", amount=to_amount, price=buy_price, fee=0.0))
            special_events.append(SpecialEvent(date=date, asset=f"{from_asset}->{to_asset}", event_type="convert", amount=from_amount, price=sell_price, fee=fee, notes=notes))
            continue

        if tx_type == "receive":
            # Receiving crypto from external wallet — creates a buy lot at market price
            if amount > 0:
                buy_price = price if price > 0 else 0.0
                trades.append(Trade(date=date, asset=asset, type="buy", amount=amount, price=buy_price, fee=0.0))
                special_events.append(SpecialEvent(date=date, asset=asset, event_type="receive", amount=amount, price=buy_price, fee=0.0, notes=notes))
            continue

        if tx_type == "send":
            # Sending to external wallet — NOT a taxable disposal
            special_events.append(SpecialEvent(date=date, asset=asset, event_type="send", amount=amount, price=price, fee=fee, notes=notes))
            continue

        # Catch-all for unknown types
        special_events.append(SpecialEvent(date=date, asset=asset or "UNKNOWN", event_type=tx_type, amount=amount, price=price, fee=fee, notes=notes))

    return trades, special_events, raw_rows


def _load_uphold_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
    skip_uphold_in: bool = False,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    trades: List[Trade] = []
    special_events: List[SpecialEvent] = []
    raw_rows: List[Dict] = []

    header_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "Date" in stripped and "Destination" in stripped:
            header_index = i
            break
    if header_index is None:
        raise ValueError("Could not find a valid Uphold CSV header.")

    reader = csv.DictReader(lines[header_index:], delimiter=",")

    for row in reader:
        if not row:
            continue

        date_str = _safe_text(row.get("Date"))
        tx_type = _safe_text(row.get("Type")).lower()
        origin_asset = _safe_text(row.get("Origin Currency")).upper()
        dest_asset = _safe_text(row.get("Destination Currency")).upper()

        if not date_str:
            continue

        try:
            date = datetime.strptime(date_str, "%a %b %d %Y %H:%M:%S %Z%z")
        except ValueError:
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                continue

        # Normalize to UTC naive so dates can be compared with Coinbase/Revolut dates
        date = _to_utc_naive(date)

        origin_amount = _clean_amount(row.get("Origin Amount"))
        dest_amount = _clean_amount(row.get("Destination Amount"))
        fee_amount = _clean_amount(row.get("Fee Amount"))

        raw_rows.append({
            "date": date,
            "tx_type": tx_type,
            "origin_asset": origin_asset,
            "dest_asset": dest_asset,
            "origin_amount": origin_amount,
            "dest_amount": dest_amount,
            "fee_amount": fee_amount,
            "source_row": row,
            "exchange": "Uphold",
        })

        # ── "in" ─────────────────────────────────────────────────────────────
        # Covers external deposits AND same-asset credits (Brave Rewards BAT).
        # Destination Currency can be empty in some staking rows — fall back to Origin.
        if tx_type == "in":
            if dest_asset and not _is_fiat(dest_asset) and dest_amount > 0:
                crypto_asset = dest_asset
                crypto_amount = dest_amount
            elif origin_asset and not _is_fiat(origin_asset) and origin_amount > 0:
                crypto_asset = origin_asset
                crypto_amount = origin_amount
            else:
                continue

            if skip_uphold_in:
                special_events.append(SpecialEvent(
                    date=date, asset=crypto_asset, event_type="skipped_deposit",
                    amount=crypto_amount, price=0.0, fee=0.0,
                    notes="deposit skipped (--skip-uphold-in): already counted in source exchange CSV",
                ))
            else:
                price = 0.0
                if price_loader and price_loader.has_asset(crypto_asset):
                    loaded_price = price_loader.get_price(crypto_asset, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=crypto_asset, type="buy", amount=crypto_amount, price=price, fee=0.0))

        # ── "staking-reward" / "reward" ───────────────────────────────────────
        elif tx_type in {"staking-reward", "reward"}:
            if dest_asset and not _is_fiat(dest_asset) and dest_amount > 0:
                crypto_asset = dest_asset
                crypto_amount = dest_amount
            elif origin_asset and not _is_fiat(origin_asset) and origin_amount > 0:
                crypto_asset = origin_asset
                crypto_amount = origin_amount
            else:
                continue

            price = 0.0
            if price_loader and price_loader.has_asset(crypto_asset):
                loaded_price = price_loader.get_price(crypto_asset, date)
                if loaded_price is not None:
                    price = loaded_price
            trades.append(Trade(date=date, asset=crypto_asset, type="buy", amount=crypto_amount, price=price, fee=0.0))
            special_events.append(SpecialEvent(date=date, asset=crypto_asset, event_type=tx_type, amount=crypto_amount, price=price, fee=0.0, notes=""))

        # ── "out": withdrawal — NOT a taxable disposal ────────────────────────
        elif tx_type == "out":
            if origin_asset and origin_amount > 0 and not _is_fiat(origin_asset):
                special_events.append(SpecialEvent(
                    date=date, asset=origin_asset, event_type="withdrawal",
                    amount=origin_amount, price=0.0, fee=fee_amount,
                    notes="transfer to external wallet — not a taxable disposal",
                ))

        # ── "transfer": internal card-to-card swap ────────────────────────────
        elif tx_type == "transfer":
            if not origin_asset or not dest_asset:
                continue
            if origin_amount <= 0 or dest_amount <= 0:
                continue

            origin_is_fiat = _is_fiat(origin_asset)
            dest_is_fiat = _is_fiat(dest_asset)

            if origin_asset == dest_asset:
                if not origin_is_fiat:
                    special_events.append(SpecialEvent(date=date, asset=origin_asset, event_type="internal_transfer", amount=origin_amount, price=0.0, fee=fee_amount, notes=""))

            elif origin_is_fiat and not dest_is_fiat:
                buy_price = origin_amount / dest_amount
                if price_loader and price_loader.has_asset(dest_asset):
                    loaded = price_loader.get_price(dest_asset, date)
                    if loaded is not None:
                        buy_price = loaded
                trades.append(Trade(date=date, asset=dest_asset, type="buy", amount=dest_amount, price=buy_price, fee=fee_amount))

            elif not origin_is_fiat and dest_is_fiat:
                sell_price = dest_amount / origin_amount
                if price_loader and price_loader.has_asset(origin_asset):
                    loaded = price_loader.get_price(origin_asset, date)
                    if loaded is not None:
                        sell_price = loaded
                trades.append(Trade(date=date, asset=origin_asset, type="sell", amount=origin_amount, price=sell_price, fee=fee_amount))

            elif not origin_is_fiat and not dest_is_fiat:
                sell_price = 0.0
                if price_loader and price_loader.has_asset(origin_asset):
                    loaded = price_loader.get_price(origin_asset, date)
                    if loaded is not None:
                        sell_price = loaded
                buy_price = 0.0
                if price_loader and price_loader.has_asset(dest_asset):
                    loaded = price_loader.get_price(dest_asset, date)
                    if loaded is not None:
                        buy_price = loaded
                trades.append(Trade(date=date, asset=origin_asset, type="sell", amount=origin_amount, price=sell_price, fee=fee_amount))
                trades.append(Trade(date=date, asset=dest_asset, type="buy", amount=dest_amount, price=buy_price, fee=0.0))
                special_events.append(SpecialEvent(date=date, asset=f"{origin_asset}->{dest_asset}", event_type="swap", amount=origin_amount, price=sell_price, fee=fee_amount, notes=""))

    return trades, special_events, raw_rows


def _load_revolut_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    trades: List[Trade] = []
    special_events: List[SpecialEvent] = []
    raw_rows: List[Dict] = []

    header_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("Completed Date,Description,Paid Out,Paid In"):
            header_index = i
            break
    if header_index is None:
        raise ValueError("Could not find a valid Revolut CSV header.")

    reader = csv.DictReader(lines[header_index:])

    for row in reader:
        if not row:
            continue

        date_str = _safe_text(row.get("Completed Date"))
        description = _safe_text(row.get("Description")).lower()
        paid_out_currency = _safe_text(row.get("Paid Out Currency")).upper()
        paid_in_currency = _safe_text(row.get("Paid In Currency")).upper()

        if not date_str:
            continue

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                continue

        date = _to_utc_naive(date)

        paid_out = _clean_amount(row.get("Paid Out"))
        paid_in = _clean_amount(row.get("Paid In"))
        exchange_rate = float(row.get("Exchange Rate", "0") or "0") or None

        raw_rows.append({
            "date": date,
            "description": description,
            "paid_out_currency": paid_out_currency,
            "paid_in_currency": paid_in_currency,
            "paid_out": paid_out,
            "paid_in": paid_in,
            "exchange_rate": exchange_rate,
            "source_row": row,
            "exchange": "Revolut",
        })

        out_is_fiat = _is_fiat(paid_out_currency)
        in_is_fiat = _is_fiat(paid_in_currency)

        if paid_out_currency == paid_in_currency:
            if paid_in > 0 and not in_is_fiat:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_in_currency):
                    loaded_price = price_loader.get_price(paid_in_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=paid_in_currency, type="buy", amount=paid_in, price=price, fee=0.0))
            if paid_out > 0 and not out_is_fiat:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_out_currency):
                    loaded_price = price_loader.get_price(paid_out_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=paid_out_currency, type="sell", amount=paid_out, price=price, fee=0.0))
        else:
            if paid_out > 0 and paid_in > 0:
                if out_is_fiat and not in_is_fiat:
                    buy_price = paid_out / paid_in
                    if price_loader and price_loader.has_asset(paid_in_currency):
                        loaded_price = price_loader.get_price(paid_in_currency, date)
                        if loaded_price is not None:
                            buy_price = loaded_price
                    trades.append(Trade(date=date, asset=paid_in_currency, type="buy", amount=paid_in, price=buy_price, fee=0.0))

                elif not out_is_fiat and in_is_fiat:
                    sell_price = paid_in / paid_out
                    if price_loader and price_loader.has_asset(paid_out_currency):
                        loaded_price = price_loader.get_price(paid_out_currency, date)
                        if loaded_price is not None:
                            sell_price = loaded_price
                    trades.append(Trade(date=date, asset=paid_out_currency, type="sell", amount=paid_out, price=sell_price, fee=0.0))

                elif not out_is_fiat and not in_is_fiat:
                    sell_price = 0.0
                    if price_loader and price_loader.has_asset(paid_out_currency):
                        loaded_price = price_loader.get_price(paid_out_currency, date)
                        if loaded_price is not None:
                            sell_price = loaded_price
                    buy_price = 0.0
                    if price_loader and price_loader.has_asset(paid_in_currency):
                        loaded_price = price_loader.get_price(paid_in_currency, date)
                        if loaded_price is not None:
                            buy_price = loaded_price
                    trades.append(Trade(date=date, asset=paid_out_currency, type="sell", amount=paid_out, price=sell_price, fee=0.0))
                    trades.append(Trade(date=date, asset=paid_in_currency, type="buy", amount=paid_in, price=buy_price, fee=0.0))
                    special_events.append(SpecialEvent(date=date, asset=f"{paid_out_currency}->{paid_in_currency}", event_type="exchange", amount=paid_out, price=sell_price, fee=0.0, notes=description))

            elif paid_in > 0 and paid_in_currency and not in_is_fiat:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_in_currency):
                    loaded_price = price_loader.get_price(paid_in_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=paid_in_currency, type="buy", amount=paid_in, price=price, fee=0.0))

            elif paid_out > 0 and paid_out_currency and not out_is_fiat:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_out_currency):
                    loaded_price = price_loader.get_price(paid_out_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=paid_out_currency, type="sell", amount=paid_out, price=price, fee=0.0))

    return trades, special_events, raw_rows
