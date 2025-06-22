Stonks!

tree -I "venv|__pycache__|*.egg-info" -L 2

python cli.py fetch	stonks fetch
python cli.py anal	stonks anal
python cli.py check-span	stonks span
python cli.py wipe-imports	stonks wipe-imports
python cli.py wipe-anal		stonks wipe-anal

#updating directories
find stonkslib -type f -name "*.py" -exec sed -i 's/from project\./from stonkslib./g' {} +
find stonkslib -type f -name "*.py" -exec sed -i 's/import project\./import stonkslib./g' {} +
sed -i 's/detect_func/find_func/g' ../stonkslib/patterns/pattern_score.py



New Folder Structure (restructure.py)
stonks/                        # 🧠 Root project folder (Git repo, readme, setup files)
│
├── stonkslib/                 # 🔧 Core Python package with all logic
│   ├── __init__.py            # Makes this a Python package
│   ├── alerts/                # 🔔 Alert generation logic (e.g. trade signals)
│   ├── execution/             # ⚙️ Trade execution logic (future expansion)
│   ├── indicators/            # 📈 Technical indicators (MACD, RSI, etc.)
│   ├── llm_integration/       # 🤖 LLM-driven analysis modules (optional)
│   ├── patterns/              # 🧠 Chart pattern detection (H&S, triangles, etc.)
│   ├── trading_logic/         # 🧾 Trading rules or backtesting strategies
│   ├── utils.py               # 🧰 Shared utility functions
│   ├── stonks.py              # 🏁 Optional central script for advanced logic
│   ├── stonks_cli.py          # 🖥️ Main CLI entry (used by `stonks` command)
│   ├── fetch_data.py          # 📡 Fetch ticker data from yfinance
│   └── check_data_span.py     # 📅 Check coverage and gaps in ticker data
│
├── data/                      # 📦 Data folder (excluded from Git)
│   ├── ticker_data/           # 📊 Raw market data organized by interval
│   │   ├── 1min/              # 1-minute data (last 5 days)
│   │   ├── 2min/              # 2-minute data (last 60 days)
│   │   ├── 5min/              # 5-minute data (last 60 days)
│   │   ├── 15min/             # 15-minute data (last 60 days)
│   │   ├── 1h/                # Hourly data (last 2 years)
│   │   ├── 1d/                # Daily data (last 5 years)
│   │   └── 1wk/               # Weekly data (last 10 years)
│   └── charts/                # 🖼️ Pattern visualization charts
│       ├── head_shoulders/    # Head & Shoulders pattern charts
│       ├── double_tops/       # Double Top pattern charts
│       ├── double_bottoms/    # Double Bottom pattern charts
│       ├── triangles/         # Triangle pattern charts
│       └── wedges/            # Wedge pattern charts
│
├── dev/                      #  🧪 Dev tools, scripts, experiments
│   ├── restructure.py         # Folder organizing helper
│   ├── restructurev2.py       # (alt version or in-progress version)
│   └── test_*.py              # Temporary test scripts
├── tickers.yaml               # 📋 Your only config file — list of tickers
├── .gitignore                 # 🔒 Ignores __pycache__, .egg-info/, venv/, etc.
├── pyproject.toml             # 📦 Modern Python build system file
├── setup.py                   # 🛠️ Legacy setup for `pip install`
├── readme.txt                 # 📘 Basic usage or project overview
└── venv/                      # 🐍 Local virtual environment (never committed)



yfinance intervals
| Interval | Description    | Limitations              |
| -------- | -------------- | ------------------------ |
| `1m`     | 1-minute data  | Up to **7 days** of data |
| `2m`     | 2-minute data  | Up to 60 days            |
| `5m`     | 5-minute data  | Up to 60 days            |
| `15m`    | 15-minute data | Up to 60 days            |
| `1h`     | Hourly data    | Up to 730 days           |
| `1d`     | Daily OHLC     | Full history             |
| `1wk`    | Weekly OHLC    | Full history             |
| `1mo`    | Monthly OHLC   | Full history             |
