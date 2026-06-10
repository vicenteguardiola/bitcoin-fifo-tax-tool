from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from btc_tool.models import SpecialEvent, Trade
from btc_tool.io.price_loader import PriceLoader


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


def detect_exchange_format(lines: List[str]) -> str:
    """Detect which exchange format the CSV is in."""
    for line in lines[:50]:  # Check first 50 lines
        stripped = line.strip()
        
        # Coinbase formats
        if stripped.startswith("ID,Timestamp,Transaction Type,Asset"):
            return "coinbase"
        if stripped.startswith("Timestamp,Transaction Type,Asset"):
            return "coinbase"
        
        # Uphold format (semicolon delimited)
        if "Date" in stripped and "Destination" in stripped and "Origin" in stripped:
            return "uphold"
        
        # Revolut format
        if stripped.startswith("Completed Date,Description,Paid Out,Paid In"):
            return "revolut"
    
    raise ValueError("Could not detect CSV format. Supported formats: Coinbase, Uphold, Revolut")


def load_trades_from_csv(
    path: str | Path,
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    """Load trades from CSV, auto-detecting the exchange format."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("CSV file is empty.")

    exchange = detect_exchange_format(lines)

    if exchange == "coinbase":
        return _load_coinbase_csv(lines, price_loader)
    elif exchange == "uphold":
        return _load_uphold_csv(lines, price_loader)
    elif exchange == "revolut":
        return _load_revolut_csv(lines, price_loader)
    else:
        raise ValueError(f"Unknown exchange format: {exchange}")


def _load_coinbase_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    """Load Coinbase CSV format."""
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
                "exchange": "Coinbase",
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


def _load_uphold_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    """
    Load Uphold CSV format (semicolon-delimited).
    
    Columns: Date,Destination,Destination Amount,Destination Currency,Fee Amount,Fee Currency,Id,
             Origin,Origin Amount,Origin Currency,Status,Type
    """
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

        origin_amount = _clean_amount(row.get("Origin Amount"))
        dest_amount = _clean_amount(row.get("Destination Amount"))
        fee_amount = _clean_amount(row.get("Fee Amount"))
        
        raw_rows.append(
            {
                "date": date,
                "tx_type": tx_type,
                "origin_asset": origin_asset,
                "dest_asset": dest_asset,
                "origin_amount": origin_amount,
                "dest_amount": dest_amount,
                "fee_amount": fee_amount,
                "source_row": row,
                "exchange": "Uphold",
            }
        )

        # Handle different transaction types
        if tx_type in {"in", "staking-reward", "reward"}:
            # Incoming transaction (deposit, staking reward, etc.)
            if dest_asset and dest_amount > 0:
                price = 0.0
                
                # Try to get price from price loader
                if price_loader and price_loader.has_asset(dest_asset):
                    loaded_price = price_loader.get_price(dest_asset, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=dest_asset,
                        type="buy",
                        amount=dest_amount,
                        price=price,
                        fee=0.0,
                    )
                )
                
                # Create special event for staking/reward
                if "reward" in tx_type or "staking" in tx_type:
                    special_events.append(
                        SpecialEvent(
                            date=date,
                            asset=dest_asset,
                            event_type=tx_type,
                            amount=dest_amount,
                            price=price,
                            fee=0.0,
                            notes="",
                        )
                    )
        
        elif tx_type in {"out", "transfer"}:
            # Outgoing transaction (withdrawal, transfer out)
            if origin_asset and origin_amount > 0:
                price = 0.0
                
                # Try to get price from price loader
                if price_loader and price_loader.has_asset(origin_asset):
                    loaded_price = price_loader.get_price(origin_asset, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=origin_asset,
                        type="sell",
                        amount=origin_amount,
                        price=price,
                        fee=fee_amount,
                    )
                )
        
        elif tx_type == "transfer":
            # Crypto-to-crypto transfer/swap
            if origin_asset and dest_asset and origin_asset != dest_asset:
                if origin_amount > 0 and dest_amount > 0:
                    # Calculate implied price
                    price = origin_amount / dest_amount if dest_amount > 0 else 0
                    
                    # Try to override with price loader
                    if price_loader and price_loader.has_asset(origin_asset):
                        loaded_price = price_loader.get_price(origin_asset, date)
                        if loaded_price is not None:
                            price = loaded_price
                    
                    trades.append(
                        Trade(
                            date=date,
                            asset=origin_asset,
                            type="sell",
                            amount=origin_amount,
                            price=price,
                            fee=fee_amount,
                        )
                    )
                    
                    trades.append(
                        Trade(
                            date=date,
                            asset=dest_asset,
                            type="buy",
                            amount=dest_amount,
                            price=price,
                            fee=0.0,
                        )
                    )
                    
                    special_events.append(
                        SpecialEvent(
                            date=date,
                            asset=f"{origin_asset}->{dest_asset}",
                            event_type="transfer",
                            amount=origin_amount,
                            price=price,
                            fee=fee_amount,
                            notes="",
                        )
                    )

    return trades, special_events, raw_rows


def _load_revolut_csv(
    lines: List[str],
    price_loader: Optional[PriceLoader] = None,
) -> Tuple[List[Trade], List[SpecialEvent], List[Dict]]:
    """
    Load Revolut CSV format.
    
    Expected columns: Completed Date, Description, Paid Out, Paid In, Exchange Rate, 
                     Paid Out Currency, Paid In Currency, Transaction ID
    """
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

        paid_out = _clean_amount(row.get("Paid Out"))
        paid_in = _clean_amount(row.get("Paid In"))
        exchange_rate = float(row.get("Exchange Rate", "0") or "0") or None

        raw_rows.append(
            {
                "date": date,
                "description": description,
                "paid_out_currency": paid_out_currency,
                "paid_in_currency": paid_in_currency,
                "paid_out": paid_out,
                "paid_in": paid_in,
                "exchange_rate": exchange_rate,
                "source_row": row,
                "exchange": "Revolut",
            }
        )

        # Detect transaction type from description and currencies
        if paid_out_currency == paid_in_currency:
            # Same currency transfer
            if paid_in > 0:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_in_currency):
                    loaded_price = price_loader.get_price(paid_in_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=paid_in_currency,
                        type="buy",
                        amount=paid_in,
                        price=price,
                        fee=0.0,
                    )
                )
            if paid_out > 0:
                price = 0.0
                if price_loader and price_loader.has_asset(paid_out_currency):
                    loaded_price = price_loader.get_price(paid_out_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=paid_out_currency,
                        type="sell",
                        amount=paid_out,
                        price=price,
                        fee=0.0,
                    )
                )
        else:
            # Cross-currency exchange
            if paid_out > 0 and paid_in > 0:
                sell_price = paid_out / paid_in if paid_in > 0 else 0
                
                # Try to override sell price with price loader
                if price_loader and price_loader.has_asset(paid_out_currency):
                    loaded_price = price_loader.get_price(paid_out_currency, date)
                    if loaded_price is not None:
                        sell_price = loaded_price
                
                # Sell the paid out currency
                if paid_out_currency and paid_out_currency != "":
                    trades.append(
                        Trade(
                            date=date,
                            asset=paid_out_currency,
                            type="sell",
                            amount=paid_out,
                            price=sell_price,
                            fee=0.0,
                        )
                    )
                
                # Buy the paid in currency
                if paid_in_currency and paid_in_currency != "":
                    buy_price = paid_out / paid_in if paid_in > 0 else 0
                    if price_loader and price_loader.has_asset(paid_in_currency):
                        loaded_price = price_loader.get_price(paid_in_currency, date)
                        if loaded_price is not None:
                            buy_price = loaded_price
                    
                    trades.append(
                        Trade(
                            date=date,
                            asset=paid_in_currency,
                            type="buy",
                            amount=paid_in,
                            price=buy_price,
                            fee=0.0,
                        )
                    )
                
                special_events.append(
                    SpecialEvent(
                        date=date,
                        asset=f"{paid_out_currency}->{paid_in_currency}",
                        event_type="exchange",
                        amount=paid_out,
                        price=sell_price,
                        fee=0.0,
                        notes=description,
                    )
                )
            elif paid_in > 0 and paid_in_currency:
                # Inbound transaction
                price = 0.0
                if price_loader and price_loader.has_asset(paid_in_currency):
                    loaded_price = price_loader.get_price(paid_in_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=paid_in_currency,
                        type="buy",
                        amount=paid_in,
                        price=price,
                        fee=0.0,
                    )
                )
            elif paid_out > 0 and paid_out_currency:
                # Outbound transaction
                price = 0.0
                if price_loader and price_loader.has_asset(paid_out_currency):
                    loaded_price = price_loader.get_price(paid_out_currency, date)
                    if loaded_price is not None:
                        price = loaded_price
                
                trades.append(
                    Trade(
                        date=date,
                        asset=paid_out_currency,
                        type="sell",
                        amount=paid_out,
                        price=price,
                        fee=0.0,
                    )
                )

    return trades, special_events, raw_rows
