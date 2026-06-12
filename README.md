## Usage

```bash
python app.py --files data/coinbase.csv data/uphold.csv data/revolut.csv \
              --price-dir data/prices/
```

### Multi-exchange support

Pasa uno o varios CSVs con `--files`. El formato se detecta automáticamente:
- **Coinbase** (exportación estándar y Advanced Trade)
- **Uphold**
- **Revolut**

Todos los trades se fusionan y ordenan cronológicamente antes de aplicar FIFO.

### Evitar lotes duplicados al transferir entre exchanges

Si moviste crypto de **Coinbase → Uphold**, el CSV de Coinbase ya contiene el lote de compra original. El CSV de Uphold también tendrá una fila `"in"` (depósito) para esa misma crypto. Cargar ambos CSVs sin ajuste contaría ese lote **dos veces**.

Usa `--skip-uphold-in` para suprimir las filas de depósito de Uphold:

```bash
python app.py --files data/coinbase.csv data/uphold.csv \
              --price-dir data/prices/ \
              --skip-uphold-in
```

Con este flag, cada transacción `"in"` de Uphold se registra como evento especial `skipped_deposit` (visible en el audit trail) pero **no** añade un lote de compra a la cola FIFO.

> **No uses `--skip-uphold-in`** si Uphold es tu único origen de datos, ya que perderías todos tus lotes de compra.

### Datos de precios históricos

Para exchanges que no incluyen precio en EUR (p.ej. Uphold), proporciona CSVs diarios de CoinMarketCap:

```bash
# Directorio completo (ficheros nombrados *_ASSET.csv)
python app.py --files data/uphold.csv --price-dir data/prices/

# O ficheros individuales
python app.py --files data/uphold.csv --prices data/prices/btc.csv data/prices/eth.csv
```
