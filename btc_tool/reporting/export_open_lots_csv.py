from pathlib import Path
import csv


def export_open_lots_csv(open_lots, out_path: str = "outputs/open_lots.csv") -> str:
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["asset", "date", "amount", "price", "fee"]

    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for lot in open_lots:
            writer.writerow(
                {
                    "asset": lot.get("asset"),
                    "date": lot.get("date"),
                    "amount": lot.get("amount"),
                    "price": lot.get("price"),
                    "fee": lot.get("fee", 0.0),
                }
            )

    return str(out_file)