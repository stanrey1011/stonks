import pandas as pd
import numpy as np


def supertrend(df, period=10, multiplier=3.0):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    hl_avg = (high + low) / 2
    upper_band = hl_avg + multiplier * atr
    lower_band = hl_avg - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)  # 1 = bullish, -1 = bearish

    for i in range(1, len(df)):
        # Upper band
        if upper_band.iloc[i] < upper_band.iloc[i - 1] or close.iloc[i - 1] > upper_band.iloc[i - 1]:
            upper_band.iloc[i] = upper_band.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Lower band
        if lower_band.iloc[i] > lower_band.iloc[i - 1] or close.iloc[i - 1] < lower_band.iloc[i - 1]:
            lower_band.iloc[i] = lower_band.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        # Direction
        if i == 1:
            direction.iloc[i] = 1
        elif supertrend.iloc[i - 1] == upper_band.iloc[i - 1]:
            direction.iloc[i] = -1 if close.iloc[i] > upper_band.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if close.iloc[i] < lower_band.iloc[i] else -1

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return pd.DataFrame({
        "Supertrend": supertrend,
        "Direction": direction,  # 1=bullish, -1=bearish
        "Upper_Band": upper_band,
        "Lower_Band": lower_band,
    }, index=df.index)
