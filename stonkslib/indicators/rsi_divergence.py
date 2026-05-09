import pandas as pd
from stonkslib.indicators.rsi import rsi as calc_rsi


def rsi_divergence(df, period=14, lookback=20):
    """
    Detect RSI divergence over the last `lookback` bars.

    Bullish divergence: price makes lower low, RSI makes higher low → potential reversal up
    Bearish divergence: price makes higher high, RSI makes lower high → potential reversal down

    Returns a DataFrame with columns:
      Bullish_Divergence: bool
      Bearish_Divergence: bool
      RSI: the RSI series
    """
    rsi_series = calc_rsi(df.copy(), period=period)
    close = df["Close"]

    bullish = pd.Series(False, index=df.index)
    bearish = pd.Series(False, index=df.index)

    for i in range(lookback, len(df)):
        window_close = close.iloc[i - lookback: i + 1]
        window_rsi = rsi_series.iloc[i - lookback: i + 1]

        if window_close.isna().any() or window_rsi.isna().any():
            continue

        current_close = close.iloc[i]
        current_rsi = rsi_series.iloc[i]
        prior_close_min = window_close.iloc[:-1].min()
        prior_rsi_at_min = window_rsi.iloc[window_close.iloc[:-1].argmin()]

        # Bullish: price lower low, RSI higher low
        if current_close < prior_close_min and current_rsi > prior_rsi_at_min:
            bullish.iloc[i] = True

        prior_close_max = window_close.iloc[:-1].max()
        prior_rsi_at_max = window_rsi.iloc[window_close.iloc[:-1].argmax()]

        # Bearish: price higher high, RSI lower high
        if current_close > prior_close_max and current_rsi < prior_rsi_at_max:
            bearish.iloc[i] = True

    return pd.DataFrame({
        "Bullish_Divergence": bullish,
        "Bearish_Divergence": bearish,
        "RSI": rsi_series,
    }, index=df.index)
