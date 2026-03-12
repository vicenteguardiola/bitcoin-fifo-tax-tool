# Bitcoin FIFO Tax Tool

Python CLI tool for parsing Coinbase CSV transaction exports and calculating
cryptocurrency gains and losses using the **FIFO (First In, First Out)** method.

The tool analyzes buy and sell transactions, matches trades using FIFO logic,
and generates simple tax-relevant reports.

---

## Overview

This project provides a lightweight command-line tool to:

* parse Coinbase CSV transaction exports
* match trades using FIFO
* calculate profit and loss
* classify taxable vs tax-free transactions
* export detailed reports

The goal is to create a simple, transparent crypto transaction analyzer that can be extended later with additional exchanges and features.

---

## Features

* Coinbase CSV transaction parsing
* FIFO trade matching engine
* Profit / loss calculation
* Taxable vs tax-free classification
* Staking / reward detection
* Report generation
* CSV exports
* Pytest test suite

---

## Project Structure

```
bitcoin-fifo-tax-tool
│
├─ btc_tool
│   ├─ engine
│   │   ├─ fifo.py
│   │   └─ staking.py
│   │
│   ├─ io
│   │   └─ csv_loader.py
│   │
│   ├─ reporting
│   │   ├─ export_audit_csv.py
│   │   ├─ export_open_lots_csv.py
│   │   ├─ export_summary_txt.py
│   │   └─ tax_report.py
│   │
│   ├─ models.py
│   └─ tax_rules.py
│
├─ tests
│   └─ test_fifo.py
│
├─ app.py
├─ pytest.ini
└─ README.md
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/acekent01/bitcoin-fifo-tax-tool.git
cd bitcoin-fifo-tax-tool
```

Optional: create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

Install dependencies if required:

```bash
pip install -r requirements.txt
```

---

## Usage

Run with the default CSV file:

```bash
python app.py
```

Run with a specific Coinbase CSV file:

```bash
python app.py --file data/coinbase.csv
```

---

## Running Tests

Run the test suite with:

```bash
pytest
```

---

## Output

The tool generates reports inside:

```
outputs/
```

Generated files:

```
audit.csv
open_lots.csv
summary.txt
```

These reports include:

* matched buy/sell trades
* profit and loss calculations
* open positions
* summarized results

---

## Example Workflow

1. Export your transaction history from Coinbase as CSV
2. Place the file inside the `data/` directory
3. Run:

```bash
python app.py --file data/coinbase.csv
```

4. Review the generated reports in the `outputs/` folder

---

## Status

Work in progress.

Planned improvements:

* multi-asset support
* better staking handling
* additional exchange formats
* improved tax classification
* decimal precision improvements

---

## Disclaimer

This project is for educational purposes only.

It does **not** provide financial or tax advice.
Always consult a professional tax advisor for official reporting.
