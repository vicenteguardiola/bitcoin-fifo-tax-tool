from datetime import datetime

import pytest

from btc_tool.engine.fifo import calculate_fifo
from btc_tool.models import Trade


def make_trade(date_str, asset, trade_type, amount, price, fee=0.0):
    return Trade(
        date=datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S"),
        asset=asset,
        type=trade_type,
        amount=amount,
        price=price,
        fee=fee,
    )


def test_fifo_simple_single_buy_single_sell():
    trades = [
        make_trade("2026-01-01 10:00:00", "BTC", "buy", 1.0, 10000.0, 0.0),
        make_trade("2026-02-01 10:00:00", "BTC", "sell", 0.4, 12000.0, 0.0),
    ]

    total_profit, matches, open_lots = calculate_fifo(trades)

    assert len(matches) == 1
    assert matches[0].sell_amount == 0.4
    assert matches[0].buy_price == 10000.0
    assert matches[0].sell_price == 12000.0
    assert round(matches[0].profit, 2) == 800.00
    assert round(total_profit, 2) == 800.00

    assert len(open_lots) == 1
    assert round(open_lots[0]["amount"], 8) == 0.6
    assert open_lots[0]["asset"] == "BTC"


def test_fifo_uses_oldest_lot_first():
    trades = [
        make_trade("2026-01-01 10:00:00", "BTC", "buy", 1.0, 10000.0, 0.0),
        make_trade("2026-01-10 10:00:00", "BTC", "buy", 1.0, 20000.0, 0.0),
        make_trade("2026-02-01 10:00:00", "BTC", "sell", 1.5, 30000.0, 0.0),
    ]

    total_profit, matches, open_lots = calculate_fifo(trades)

    assert len(matches) == 2

    assert matches[0].buy_date == datetime(2026, 1, 1, 10, 0, 0)
    assert matches[0].sell_amount == 1.0
    assert round(matches[0].profit, 2) == 20000.00

    assert matches[1].buy_date == datetime(2026, 1, 10, 10, 0, 0)
    assert matches[1].sell_amount == 0.5
    assert round(matches[1].profit, 2) == 5000.00

    assert round(total_profit, 2) == 25000.00

    assert len(open_lots) == 1
    assert round(open_lots[0]["amount"], 8) == 0.5
    assert round(open_lots[0]["price"], 2) == 20000.00


def test_fifo_partial_sell_keeps_remaining_lot():
    trades = [
        make_trade("2026-01-01 10:00:00", "BTC", "buy", 2.0, 15000.0, 0.0),
        make_trade("2026-01-15 10:00:00", "BTC", "sell", 0.75, 18000.0, 0.0),
    ]

    total_profit, matches, open_lots = calculate_fifo(trades)

    assert len(matches) == 1
    assert matches[0].sell_amount == 0.75
    assert round(matches[0].profit, 2) == 2250.00
    assert round(total_profit, 2) == 2250.00

    assert len(open_lots) == 1
    assert round(open_lots[0]["amount"], 8) == 1.25
    assert open_lots[0]["asset"] == "BTC"


def test_fifo_separates_assets():
    trades = [
        make_trade("2026-01-01 10:00:00", "BTC", "buy", 1.0, 10000.0, 0.0),
        make_trade("2026-01-02 10:00:00", "ETH", "buy", 2.0, 2000.0, 0.0),
        make_trade("2026-02-01 10:00:00", "BTC", "sell", 0.5, 12000.0, 0.0),
    ]

    total_profit, matches, open_lots = calculate_fifo(trades)

    assert len(matches) == 1
    assert matches[0].asset == "BTC"
    assert round(matches[0].profit, 2) == 1000.00
    assert round(total_profit, 2) == 1000.00

    assert len(open_lots) == 2

    btc_lots = [lot for lot in open_lots if lot["asset"] == "BTC"]
    eth_lots = [lot for lot in open_lots if lot["asset"] == "ETH"]

    assert len(btc_lots) == 1
    assert len(eth_lots) == 1
    assert round(btc_lots[0]["amount"], 8) == 0.5
    assert round(eth_lots[0]["amount"], 8) == 2.0


def test_fifo_raises_error_when_selling_more_than_inventory():
    trades = [
        make_trade("2026-01-01 10:00:00", "BTC", "buy", 0.5, 10000.0, 0.0),
        make_trade("2026-02-01 10:00:00", "BTC", "sell", 1.0, 12000.0, 0.0),
    ]

    with pytest.raises(ValueError, match="Insufficient inventory"):
        calculate_fifo(trades)