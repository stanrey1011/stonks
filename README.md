# Stonks Quant Dashboard

An interactive, multi-layered dashboard for visualizing and exploring price action, indicators, and pattern signals for stocks, crypto, and ETFs.  
Supports overlays for Bollinger Bands, moving averages, and more, with a simple Python-based CLI for fetching, cleaning, and analyzing your market data.

---

## Features

- Candlestick charting for any asset and interval (minute, hourly, daily, weekly)
- Overlay indicators (Bollinger Bands, Double/Triple MAs, etc.) with checkboxes
- Adjustable candle scaling for better pattern visibility
- Debug/data panel for troubleshooting
- Clean, extensible Python and Streamlit codebase
- Modular CLI for data fetching, cleaning, and signal analysis

---

## Quick Start

1. **Clone or download this repository**
    ```sh
    git clone <your-repo-url> stonks
    cd stonks
    ```
    Or just unzip/copy the folder to your machine.

2. **Edit `tickers.yaml`**  
   Add or remove the tickers, crypto pairs, and ETFs you want to analyze.  
   The format looks like:
    ```yaml
    stocks:
      - AAPL
      - MSFT
      - TSLA
      - NVDA

    crypto:
      - BTC-USD
      - ETH-USD

    etfs:
      - SPY
      - QQQ
    ```
   *(All tickers must match Yahoo Finance or your data provider’s conventions.)*

3. **Create and activate a virtual environment**
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(On Windows: `venv\Scripts\activate`)*

4. **Install required Python packages**
    ```sh
    pip install -r requirements.txt
    ```

5. **(Once per new data set) Fetch, clean, and analyze data**
    ```sh
    stonks fetch
    stonks clean
    stonks analyze
    ```

6. **Run the dashboard**
    ```sh
    streamlit run stonkslib/dash/dashboard.py
    ```
    Then open the provided URL (usually [http://localhost:8501](http://localhost:8501)) in your browser.

---

## Using the Dashboard

- Select your ticker and interval in the sidebar
- Toggle indicator overlays (Bollinger Bands, Moving Averages, etc.)
- Adjust vertical scaling to zoom in/out on candle patterns
- Open the debug expander to view raw data for troubleshooting or verification

---

## Troubleshooting

- **Missing data error?**  
  Make sure you’ve run `stonks fetch`, `stonks clean`, and `stonks analyze`, and check your `data/` directories for the expected CSVs.

- **Missing package error?**  
  Double-check you’re in your virtual environment and have run `pip install -r requirements.txt`.

- **Charts don’t show overlays?**  
  Confirm that indicator files exist for the selected ticker/interval in `data/analysis/signals/`.

---

## Development

- All indicator/pattern scripts are modular and easy to extend (see `stonkslib/indicators/`, `stonkslib/patterns/`)
- Strategies are YAML-based (see `stonkslib/strategies/`)
- CLI commands are managed in `stonkslib/stonks_cli.py`

---

## License

MIT License (see LICENSE file)

---

**Questions or improvements?**  
Open an issue or submit a pull request!

---

## Folder Structure


```

stonks/ # 🧠 Root project folder (Git repo, README, setup files)
│
├── stonkslib/ # 🔧 Core Python package (all main logic)
│ ├── init.py
│ ├── alerts/ # 🔔 Trade alert/notification logic
│ ├── analysis/ # 📊 Signal generation/analysis scripts
│ ├── backtest/ # 🔙 Backtesting engines & logic
│ ├── dash/ # 📉 Dash/Streamlit/Plotly dashboard UIs
│ ├── execution/ # ⚙️ (Optional) Trade execution for brokers/APIs
│ ├── fetch/ # 📡 Data fetching modules
│ ├── import/ # 🛂 DB import scripts (e.g. DuckDB, SQLite)
│ ├── indicators/ # 📈 Technical indicators (RSI, MACD, BB, etc.)
│ ├── llm_integration/ # 🤖 LLM helpers/integration (optional)
│ ├── merge/ # 🧬 CSV merging/combine logic
│ ├── patterns/ # 🧠 Chart pattern detectors (H&S, triangles, etc.)
│ ├── plots/ # 🖼️ Plotting/dashboard scripts (main Streamlit app)
│ ├── strategies/ # 🧾 YAML strategy configs (user-editable)
│ ├── trading_logic/ # 🔀 Rules-based or template strategies
│ ├── utils/ # 🧰 Helper modules (clean_td, load_td, etc.)
│ └── stonks_cli.py # 🖥️ Main CLI entry (stonks command)
│
├── data/ # 📦 Project data (usually in .gitignore)
│ ├── ticker_data/
│ │ ├── raw/ # Raw CSVs fetched from provider (per interval/ticker)
│ │ └── clean/ # Cleaned/standardized OHLCV CSVs (per interval/ticker)
│ ├── analysis/ # Results of indicator/pattern analysis, backtests, etc.
│ │ ├── signals/ # Per-ticker/interval indicator signals (csvs)
│ │ ├── merged/ # Merged indicator/pattern signals for LLM/modeling
│ │ └── backtests/ # Backtest results (per strategy/pattern)
│ └── charts/ # (Optional) Example chart images, visualizations, pattern samples
│
├── dev/ # 🧪 Dev scripts, migration helpers, experiments
│ ├── restructure.py
│ ├── sanity_check.sh
│ └── ... # Other dev/test scripts
│
├── tickers.yaml # 📋 Your only config file — list of tickers/crypto/etfs to fetch
├── requirements.txt # 📦 List of Python package dependencies
├── README.md # 📘 Main usage instructions and intro (this file!)
├── .gitignore # 🔒 Ignores pycache, .egg-info/, venv/, and data folders
├── pyproject.toml # 🛠️ Python project/build tool config (optional but modern)
├── setup.py # 🛠️ Legacy Python setup for pip install (if needed)
└── venv/ # 🐍 Local Python virtualenv (never committed to Git)

```

### yfinance Intervals & Lookback Limits

```

| Interval | Description     | Stocks/ETFs         | Crypto (BTC/ETH-USD) |
|----------|-----------------|---------------------|----------------------|
| `1m`     | 1-minute data   | 7 days              | 7–60 days (often 60) |
| `2m`     | 2-minute data   | 60 days             | 60 days              |
| `5m`     | 5-minute data   | 60 days             | 60 days              |
| `15m`    | 15-minute data  | 60 days             | 60 days              |
| `1h`     | Hourly data     | 730 days (~2 years) | 730 days             |
| `1d`     | Daily OHLC      | Full history        | Full history         |
| `1wk`    | Weekly OHLC     | Full history        | Full history         |
| `1mo`    | Monthly OHLC    | Full history        | Full history         |

```

## Ziping the project

```

zip -r stonks_clean.zip stonks \
  -x "stonks/venv/*" \
  -x "stonks/__pycache__/*" \
  -x "stonks/*.egg-info/*" \
  -x "stonks/**/*.pyc" \
  -x "stonks/.git/*" \
  -x "stonks/dev/*" \
  -x "stonks/data/*"

```

## Other Notes

```

tree -I "venv|__pycache__|*.egg-info" -L 2

1. update ticker.yaml
2. stonks fetch - retrieves ticker data from yahoo finance (data/ticker_data/raw/{interval}/{ticker}.csv)
3. stonks clean - clean and standardize raw ticker data (data/ticker_data/clean/{interval}/{ticker}.csv)
4. stonks analyze - runs clean ticker through indicators and pattern detection (data/analysis/signals/{ticker}/{interval}/{source}.csv)
5. stonks merge - combines all indicators and patterns into a single csv (data/analysis/signals/{ticker}/{interval}/{source}.csv)

```