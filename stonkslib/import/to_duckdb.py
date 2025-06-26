# stonkslib/dash/main.py

import dash
from dash import dcc, html, Input, Output, State, callback_context
import duckdb
import pandas as pd
import plotly.graph_objs as go
import os

DB_PATH = "data/db/duckdb/signals.duckdb"

# --------- Helper functions ---------
def get_tickers():
    with duckdb.connect(DB_PATH) as con:
        rows = con.execute("SELECT DISTINCT ticker FROM signals").fetchall()
        return sorted([row[0] for row in rows])

def get_intervals(ticker):
    with duckdb.connect(DB_PATH) as con:
        rows = con.execute("SELECT DISTINCT interval FROM signals WHERE ticker = ?", [ticker]).fetchall()
        return sorted([row[0] for row in rows])

def fetch_df(ticker, interval):
    with duckdb.connect(DB_PATH) as con:
        sql = f"""
            SELECT * FROM signals
            WHERE ticker = ? AND interval = ?
            ORDER BY "Date"
        """
        df = con.execute(sql, [ticker, interval]).df()
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', utc=True)
        return df

# --------- Dash App Layout ----------
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H2("Stonks Indicators Dashboard"),
    html.Div([
        html.Label("Ticker"),
        dcc.Dropdown(
            id='ticker-dropdown',
            options=[{'label': t, 'value': t} for t in get_tickers()],
            value=get_tickers()[0] if get_tickers() else None,
            style={'width': 200}
        ),
        html.Label("Interval", style={'marginLeft': 20}),
        dcc.Dropdown(
            id='interval-dropdown',
            style={'width': 120, 'display': 'inline-block'}
        ),
        html.Label("Indicators", style={'marginLeft': 20}),
        dcc.Checklist(
            id='indicator-checklist',
            options=[
                {'label': 'Bollinger Bands', 'value': 'bollinger'},
                {'label': 'MACD', 'value': 'macd'},
                {'label': 'RSI', 'value': 'rsi'},
                {'label': 'OBV', 'value': 'obv'},
            ],
            value=['bollinger', 'macd', 'rsi'],
            inline=True,
            style={'marginTop': 6}
        ),
    ], style={'display': 'flex', 'alignItems': 'center'}),

    html.Div([
        html.Div([
            html.Label('RSI Period'),
            dcc.Slider(id='rsi-period', min=5, max=30, step=1, value=14, marks={i: str(i) for i in range(5, 31, 5)}),
        ], style={'width': '28%', 'display': 'inline-block', 'paddingRight': 15}),
        html.Div([
            html.Label('Boll Window'),
            dcc.Slider(id='boll-window', min=5, max=50, step=1, value=20, marks={i: str(i) for i in range(5, 51, 5)}),
            html.Label('Boll StdDev'),
            dcc.Slider(id='boll-std', min=1, max=3, step=0.1, value=2.0, marks={i: str(i) for i in range(1, 4)}),
        ], style={'width': '36%', 'display': 'inline-block', 'paddingRight': 15}),
        html.Div([
            html.Label('MACD Fast/Slow/Signal'),
            dcc.Input(id='macd-fast', type='number', value=12, min=2, max=50, step=1, style={'width': 45, 'marginRight': 3}),
            dcc.Input(id='macd-slow', type='number', value=26, min=2, max=100, step=1, style={'width': 45, 'marginRight': 3}),
            dcc.Input(id='macd-signal', type='number', value=9, min=2, max=50, step=1, style={'width': 45}),
        ], style={'width': '36%', 'display': 'inline-block', 'verticalAlign': 'top'}),
    ], style={'margin': '16px 0', 'display': 'flex'}),

    dcc.Graph(id='main-chart', config={'displayModeBar': True, 'scrollZoom': True})
], style={'maxWidth': 1200, 'margin': 'auto'})


# ------- Interval options update -------
@app.callback(
    Output('interval-dropdown', 'options'),
    Output('interval-dropdown', 'value'),
    Input('ticker-dropdown', 'value')
)
def update_interval_dropdown(ticker):
    if not ticker:
        return [], None
    intervals = get_intervals(ticker)
    value = intervals[0] if intervals else None
    return [{'label': i, 'value': i} for i in intervals], value

# ----------- Main Chart Update -----------
@app.callback(
    Output('main-chart', 'figure'),
    [
        Input('ticker-dropdown', 'value'),
        Input('interval-dropdown', 'value'),
        Input('indicator-checklist', 'value'),
        Input('rsi-period', 'value'),
        Input('boll-window', 'value'),
        Input('boll-std', 'value'),
        Input('macd-fast', 'value'),
        Input('macd-slow', 'value'),
        Input('macd-signal', 'value')
    ]
)
def update_chart(ticker, interval, indicators, rsi_period, boll_win, boll_std, macd_fast, macd_slow, macd_signal):
    if not ticker or not interval:
        return go.Figure()

    df = fetch_df(ticker, interval)
    if df.empty or 'Date' not in df.columns:
        return go.Figure()

    fig = go.Figure()

    # --- Close price line ---
    if 'close' in [c.lower() for c in df.columns]:
        close_col = [c for c in df.columns if c.lower() == 'close'][0]
        fig.add_trace(go.Scatter(
            x=df['Date'], y=df[close_col], mode='lines', name='Close'
        ))

    # --- Bollinger Bands ---
    if 'bollinger' in indicators:
        upper = f"BB_upper_{boll_win}_{int(boll_std)}"
        lower = f"BB_lower_{boll_win}_{int(boll_std)}"
        # fallback to search for closest columns if exact not found
        upper_col = [c for c in df.columns if c.lower().startswith('bb_upper') and str(boll_win) in c and str(int(boll_std)) in c]
        lower_col = [c for c in df.columns if c.lower().startswith('bb_lower') and str(boll_win) in c and str(int(boll_std)) in c]
        if upper_col and lower_col:
            fig.add_trace(go.Scatter(x=df['Date'], y=df[upper_col[0]], mode='lines', name='BB Upper'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df[lower_col[0]], mode='lines', name='BB Lower'))

    # --- MACD ---
    if 'macd' in indicators:
        macd_name = f"MACD_{macd_fast}_{macd_slow}_{macd_signal}"
        macd_col = [c for c in df.columns if c.upper() == macd_name]
        if macd_col:
            fig.add_trace(go.Scatter(x=df['Date'], y=df[macd_col[0]], mode='lines', name=macd_col[0]))

    # --- RSI ---
    if 'rsi' in indicators:
        rsi_col = f"RSI_{rsi_period}"
        rsi_match = [c for c in df.columns if c.upper().endswith(str(rsi_period))]
        if rsi_match:
            fig.add_trace(go.Scatter(x=df['Date'], y=df[rsi_match[0]], mode='lines', name=rsi_match[0]))

    # --- OBV ---
    if 'obv' in indicators:
        obv_col = [c for c in df.columns if 'OBV' in c.upper()]
        if obv_col:
            fig.add_trace(go.Scatter(x=df['Date'], y=df[obv_col[0]], mode='lines', name='OBV', yaxis='y2'))
            fig.update_layout(
                yaxis2=dict(
                    title='OBV',
                    overlaying='y',
                    side='right',
                    showgrid=False
                )
            )

    fig.update_layout(
        height=600,
        margin=dict(t=30, b=30, l=60, r=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        xaxis_title="Date",
        yaxis_title="Price",
    )
    return fig

if __name__ == "__main__":
    app.run(debug=True)
