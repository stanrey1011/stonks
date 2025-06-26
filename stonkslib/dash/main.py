import os
import duckdb
import pandas as pd
import plotly.graph_objs as go
from dash import Dash, dcc, html, Input, Output

DB_PATH = os.path.abspath("data/db/duckdb/signals.duckdb")

# --- Helper: Get list of tickers and intervals ---
def get_tickers():
    with duckdb.connect(DB_PATH, read_only=True) as con:
        rows = con.execute("SELECT DISTINCT ticker FROM signals").fetchall()
        return sorted([row[0] for row in rows])

def get_intervals(ticker):
    with duckdb.connect(DB_PATH, read_only=True) as con:
        rows = con.execute("SELECT DISTINCT interval FROM signals WHERE ticker = ?", (ticker,)).fetchall()
        return sorted([row[0] for row in rows])

def load_signals(ticker, interval):
    with duckdb.connect(DB_PATH, read_only=True) as con:
        df = con.execute(
            "SELECT * FROM signals WHERE ticker=? AND interval=? ORDER BY Date",
            (ticker, interval)
        ).df()
        # Standardize columns to lower-case for convenience
        df.columns = [col.lower() for col in df.columns]
        return df

app = Dash(__name__)

app.layout = html.Div([
    html.H2("Stonks Dash – Indicator Backtest Viewer"),
    html.Label("Select Ticker"),
    dcc.Dropdown(
        id='ticker-dropdown',
        options=[{'label': t, 'value': t} for t in get_tickers()],
        value=get_tickers()[0],
        clearable=False
    ),
    html.Label("Select Interval"),
    dcc.Dropdown(
        id='interval-dropdown',
        options=[],  # Populated dynamically
        value=None,
        clearable=False
    ),
    html.Div([
        html.Label("Show indicators:"),
        dcc.Checklist(
            id='indicator-checklist',
            options=[
                {"label": "MACD", "value": "macd"},
                {"label": "RSI", "value": "rsi"},
                {"label": "OBV", "value": "obv"},
                {"label": "Bollinger Bands", "value": "bollinger"},
            ],
            value=["macd", "rsi", "obv", "bollinger"],
            inline=True,
        )
    ]),
    dcc.Graph(id='main-chart', config={"displayModeBar": True}),
    html.Div(id='info-message', style={'color': 'red'})
])

@app.callback(
    Output('interval-dropdown', 'options'),
    Output('interval-dropdown', 'value'),
    Input('ticker-dropdown', 'value')
)
def update_intervals(ticker):
    intervals = get_intervals(ticker)
    opts = [{'label': i, 'value': i} for i in intervals]
    return opts, intervals[0] if intervals else None

@app.callback(
    Output('main-chart', 'figure'),
    Output('info-message', 'children'),
    Input('ticker-dropdown', 'value'),
    Input('interval-dropdown', 'value'),
    Input('indicator-checklist', 'value')
)
def update_chart(ticker, interval, selected_indicators):
    if not ticker or not interval:
        return go.Figure(), "No ticker/interval selected."

    df = load_signals(ticker, interval)
    if df.empty or 'close' not in df.columns:
        return go.Figure(), "No data available or missing 'Close' column."

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['close'], mode='lines', name='Close Price'
    ))

    info = ""
    # MACD
    if "macd" in selected_indicators:
        macd_cols = [col for col in df.columns if col.startswith("macd_macd_")]
        if macd_cols:
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[macd_cols[0]], mode='lines', name='MACD'))
        else:
            info += "MACD not available. "
    # RSI
    if "rsi" in selected_indicators:
        rsi_cols = [col for col in df.columns if col.startswith("rsi_rsi_")]
        if rsi_cols:
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[rsi_cols[0]], mode='lines', name='RSI'))
        else:
            info += "RSI not available. "
    # OBV
    if "obv" in selected_indicators:
        obv_col = [col for col in df.columns if col.startswith("obv_obv")]
        if obv_col:
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[obv_col[0]], mode='lines', name='OBV'))
        else:
            info += "OBV not available. "
    # Bollinger Bands
    if "bollinger" in selected_indicators:
        upper = [col for col in df.columns if col.startswith("bollinger_bb_upper")]
        lower = [col for col in df.columns if col.startswith("bollinger_bb_lower")]
        if upper and lower:
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[upper[0]], line=dict(dash='dash', color='gray'),
                name='BB Upper'))
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[lower[0]], line=dict(dash='dash', color='gray'),
                name='BB Lower'))
        else:
            info += "Bollinger Bands not available. "

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Price/Indicator",
        hovermode="x unified",
        template="plotly_dark",
        legend=dict(orientation="h")
    )
    return fig, info

if __name__ == "__main__":
    app.run(debug=True)
