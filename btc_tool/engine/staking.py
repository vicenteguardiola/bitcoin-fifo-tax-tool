from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Union

from btc_tool.models import SpecialEvent


def summarize_special_events(special_events: List[Union[dict, SpecialEvent]]) -> Dict[str, Dict[str, dict]]:
    summary: Dict[str, Dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "amount": 0.0})
    )

    for event in special_events:
        # Handle both dict and SpecialEvent objects
        if isinstance(event, SpecialEvent):
            event_type = (event.event_type or "unknown").strip().lower()
            asset = (event.asset or "UNKNOWN").strip().upper()
            amount = float(event.amount or 0.0)
        else:
            event_type = (event.get("event_type") or "unknown").strip().lower()
            asset = (event.get("asset") or "UNKNOWN").strip().upper()
            amount = float(event.get("amount") or 0.0)

        summary[event_type][asset]["count"] += 1
        summary[event_type][asset]["amount"] += amount

    return {event_type: dict(asset_map) for event_type, asset_map in summary.items()}


def summarize_transaction_types(raw_rows: List[dict]) -> Dict[str, int]:
    summary: Dict[str, int] = {}

    for row in raw_rows:
        tx_type = (
            row.get("transaction_type")
            or row.get("Transaction Type")
            or "unknown"
        )
        tx_type = str(tx_type).strip().lower()

        if tx_type not in summary:
            summary[tx_type] = 0

        summary[tx_type] += 1

    return summary
