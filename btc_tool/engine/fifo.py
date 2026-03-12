from __future__ import annotations

from typing import Dict, List, Tuple

from btc_tool.models import MatchRow, Trade
from btc_tool.tax_rules import (
    held_more_than_one_year,
    holding_days,
    tax_status_de,
)

EPS = 1e-12


def calculate_fifo(trades: List[Trade]) -> Tuple[float, List[MatchRow], List[Dict]]:
    """
    Berechnet FIFO für Spot-Trades mit separater Queue pro Asset.

    Rückgabe:
        total_profit: float
        matches: Liste von MatchRow
        open_lots: Liste von dicts mit date, asset, amount, price, fee
    """

    trades_sorted = sorted(trades, key=lambda t: t.date)

    buys_by_asset: Dict[str, List[Dict]] = {}
    matches: List[MatchRow] = []
    total_profit = 0.0

    for trade in trades_sorted:
        ttype = (trade.type or "").strip().lower()
        asset = trade.asset.strip().upper()

        if asset not in buys_by_asset:
            buys_by_asset[asset] = []

        asset_buys = buys_by_asset[asset]

        if ttype == "buy":
            if trade.amount <= 0:
                raise ValueError(f"BUY amount must be > 0, got {trade.amount}")
            if trade.price < 0:
                raise ValueError(f"BUY price must be >= 0, got {trade.price}")

            asset_buys.append(
                {
                    "date": trade.date,
                    "asset": asset,
                    "amount": float(trade.amount),
                    "price": float(trade.price),
                    "fee": float(trade.fee or 0.0),
                }
            )

        elif ttype == "sell":
            if trade.amount <= 0:
                raise ValueError(f"SELL amount must be > 0, got {trade.amount}")
            if trade.price < 0:
                raise ValueError(f"SELL price must be >= 0, got {trade.price}")

            sell_amount_remaining = float(trade.amount)
            sell_fee_total = float(trade.fee or 0.0)

            while sell_amount_remaining > EPS and asset_buys:
                lot = asset_buys[0]

                lot_amount = float(lot["amount"])
                if lot_amount <= EPS:
                    asset_buys.pop(0)
                    continue

                matched_amount = min(sell_amount_remaining, lot_amount)

                lot_fee_total = float(lot.get("fee", 0.0))
                buy_fee_part = (
                    lot_fee_total * (matched_amount / lot_amount)
                    if lot_amount > EPS
                    else 0.0
                )

                sell_fee_part = (
                    sell_fee_total * (matched_amount / float(trade.amount))
                    if float(trade.amount) > EPS
                    else 0.0
                )

                cost_basis = (matched_amount * float(lot["price"])) + buy_fee_part
                proceeds = (matched_amount * float(trade.price)) - sell_fee_part
                profit = proceeds - cost_basis

                days = holding_days(lot["date"], trade.date)
                held_more_than_1y = held_more_than_one_year(lot["date"], trade.date)
                tax_status = tax_status_de(lot["date"], trade.date)

                matches.append(
                    MatchRow(
                        asset=asset,
                        sell_date=trade.date,
                        sell_amount=matched_amount,
                        sell_price=float(trade.price),
                        sell_fee_part=sell_fee_part,
                        buy_date=lot["date"],
                        buy_amount=matched_amount,
                        buy_price=float(lot["price"]),
                        buy_fee_part=buy_fee_part,
                        cost_basis=cost_basis,
                        proceeds=proceeds,
                        profit=profit,
                        holding_days=days,
                        held_more_than_1y=held_more_than_1y,
                        tax_status=tax_status,
                    )
                )

                total_profit += profit

                lot["amount"] = lot_amount - matched_amount
                lot["fee"] = lot_fee_total - buy_fee_part
                sell_amount_remaining -= matched_amount

                if float(lot["amount"]) <= EPS:
                    asset_buys.pop(0)

            if sell_amount_remaining > EPS:
                sold_amount = float(trade.amount) - sell_amount_remaining
                raise ValueError(
                    f"Insufficient inventory for {asset}: tried to sell {trade.amount}, "
                    f"but only {sold_amount} was available."
                )

        else:
            raise ValueError(
                f"Unknown trade type: {trade.type!r}. Expected 'buy' or 'sell'."
            )

    open_lots: List[Dict] = []
    for asset, lots in buys_by_asset.items():
        for lot in lots:
            if float(lot["amount"]) > EPS:
                open_lots.append(
                    {
                        "date": lot["date"],
                        "asset": asset,
                        "amount": float(lot["amount"]),
                        "price": float(lot["price"]),
                        "fee": float(lot.get("fee", 0.0)),
                    }
                )

    open_lots.sort(key=lambda x: (x["asset"], x["date"]))

    return total_profit, matches, open_lots