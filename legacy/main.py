from btc_tool.io.csv_loader import load_trades
from btc_tool.engine.fifo import calculate_fifo

def main():
    print("-------------------")
    print("START: Tool läuft...")
    print("-------------------")

    trades = load_trades()
    print(f"Erfolgreich geladen: {len(trades)} Trades")

    profit = calculate_fifo(trades)
    print(f"Gesamtgewinn (FIFO): {profit:.2f} €")

if __name__ == "__main__":
    main()