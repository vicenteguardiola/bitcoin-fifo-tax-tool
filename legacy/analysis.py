import pandas as pd
from btc_tool.models import Trade

def load_trades(path="data/trades.csv"):
    # Datei laden
    df = pd.read_csv(path)
    
    # Sicherstellen, dass alle Spaltennamen kleingeschrieben sind (verhindert Fehler)
    df.columns = [c.lower() for c in df.columns]
    
    # Datum konvertieren und sortieren
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    
    trades = []
    for _, row in df.iterrows():
        trade = Trade(
            date=row["date"],
            type=row["type"],
            amount=row["amount"],
            price=row["price"],
            fee=row["fee"]
        )
        trades.append(trade)
    
    return trades
