from btc_tool.models import Trade

def calculate_fifo(trades):
    buys = []
    total_profit = 0

    for trade in trades:

        if trade.type == "buy":
            buys.append({
                "amount": trade.amount,
                "price": trade.price
            })

        elif trade.type == "sell":
            sell_amount = trade.amount

            while sell_amount > 0 and buys:
                buy = buys[0]

                if buy["amount"] <= sell_amount:
                    profit = (trade.price - buy["price"]) * buy["amount"]
                    total_profit += profit
                    sell_amount -= buy["amount"]
                    buys.pop(0)
                else:
                    profit = (trade.price - buy["price"]) * sell_amount
                    total_profit += profit
                    buy["amount"] -= sell_amount
                    sell_amount = 0

    return total_profit