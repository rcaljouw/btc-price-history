# btc-price-history

Daily BTC/USD price history (OHLCV) as a single CSV file, updated automatically every day by GitHub Actions.

## Data

File: [`data/btc-usd-daily.csv`](data/btc-usd-daily.csv)

| Column | Description |
|---|---|
| `date` | Day in UTC, ISO format (`YYYY-MM-DD`) |
| `open`, `high`, `low`, `close` | Price in USD for that UTC day |
| `volume` | Traded volume in BTC on the source exchange |
| `source` | Where the row came from (currently `bitstamp`) |

- One row per completed UTC day; the current, still-open day is never included.
- Coverage starts in August 2011 (start of Bitstamp's history).
- Raw file URL for scripts and notebooks:
  `https://raw.githubusercontent.com/rcaljouw/btc-price-history/main/data/btc-usd-daily.csv`

## How it updates

The workflow in `.github/workflows/update.yml` runs daily at 01:15 UTC. It runs `scripts/update.py`, which:

1. reads the last date in the CSV,
2. fetches only the missing days from the Bitstamp public API,
3. deduplicates, sorts and reports any gaps,
4. commits the file only if something changed.

It can also be started by hand under **Actions → Update BTC price data → Run workflow**. The first run fills the full history.

Run locally (Python 3.10+, standard library only):

```bash
python scripts/update.py
```

## Data sources & terms

| Source | Period | Terms |
|---|---|---|
| [Bitstamp public API](https://www.bitstamp.net/api/) | Aug 2011 – present | Subject to Bitstamp's API terms of use |

The data is provided **as is**, without any warranty of accuracy or completeness. Prices are from a single exchange and can differ from other exchanges or index prices, especially in the early years. Not financial advice.

## License

The code in this repository (`scripts/`, `.github/`) is licensed under the [MIT License](LICENSE).
The MIT License does not cover the price data itself; the data remains subject to the terms of its source listed above.
