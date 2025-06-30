# stonkslib/analysis/plot_backtest_trades.py

import pandas as pd
import plotly.graph_objs as go

def plot_trades(price_path, trades_path, title="Backtest Trades"):
    price = pd.read_csv(price_path, index_col=0, parse_dates=True)
    trades = pd.read_csv(trades_path)
    trades['date'] = pd.to_datetime(trades['date'])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index, y=price['Close'],
        mode='lines', name='Close Price',
        line=dict(color='blue')
    ))
    buy_trades = trades[trades['action'] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy_trades['date'],
        y=price.loc[buy_trades['date'], 'Close'],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10, color='green'),
        name='Buy',
        text=[f"BUY<br>Date: {d.strftime('%Y-%m-%d')}<br>Price: {p:.2f}" for d,p in zip(buy_trades['date'], buy_trades['price'])]
    ))
    sell_trades = trades[trades['action'].str.startswith('SELL')]
    fig.add_trace(go.Scatter(
        x=sell_trades['date'],
        y=price.loc[sell_trades['date'], 'Close'],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10, color='red'),
        name='Sell',
        text=[f"SELL<br>Date: {d.strftime('%Y-%m-%d')}<br>Price: {p:.2f}" for d,p in zip(sell_trades['date'], sell_trades['price'])]
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price",
        hovermode="closest"
    )
    fig.show()

if __name__ == "__main__":
    # Example usage
    price_path = "data/ticker_data/clean/1d/AAPL.csv"
    trades_path = "data/analysis/backtests/indicators/AAPL_1d_results.csv"
    plot_trades(price_path, trades_path, title="AAPL 1d Backtest Trades")
