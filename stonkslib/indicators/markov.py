import numpy as np
import pandas as pd


def markov_signals(df, states=3, lookback=60):
    """
    Discrete Markov chain regime detector.

    Discretizes log returns into `states` quantile bins over a rolling `lookback`
    window and builds a transition probability matrix. At each bar, returns the
    probability of transitioning from the current state to the most bullish state
    (bull_prob) and the most bearish state (bear_prob).

    Returns a DataFrame aligned to df.index with columns:
        state      - current discretized state (0=most bearish, states-1=most bullish)
        bull_prob  - P(current → top state)
        bear_prob  - P(current → bottom state)
    """
    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])
    n = len(df)

    log_ret = np.log(df["Close"] / df["Close"].shift(1)).values
    quantile_levels = np.array([j / states for j in range(1, states)])

    state_arr = np.full(n, np.nan)
    bull_arr = np.full(n, np.nan)
    bear_arr = np.full(n, np.nan)

    for i in range(lookback, n):
        window = log_ret[i - lookback : i + 1]
        if np.isnan(window).any():
            continue

        boundaries = np.quantile(window, quantile_levels)
        if len(np.unique(boundaries)) < len(boundaries):
            # degenerate window (all returns identical) — skip
            continue

        state_seq = np.digitize(window, boundaries)  # values: 0 .. states-1

        trans = np.zeros((states, states))
        for t in range(len(state_seq) - 1):
            trans[state_seq[t], state_seq[t + 1]] += 1

        row_sums = trans.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans /= row_sums

        cur = state_seq[-1]
        state_arr[i] = float(cur)
        bull_arr[i] = trans[cur, states - 1]
        bear_arr[i] = trans[cur, 0]

    return pd.DataFrame(
        {"state": state_arr, "bull_prob": bull_arr, "bear_prob": bear_arr},
        index=df.index,
    )


def _transition_matrix(log_ret, states, lookback):
    """Build a row-stochastic transition matrix from the final `lookback` window.

    Returns (T, current_state) or (None, None) on a degenerate window. Rows with no
    observed transitions fall back to a uniform distribution so T stays stochastic
    (required for the matrix-power forecast below).
    """
    valid = log_ret[~np.isnan(log_ret)]
    if len(valid) < lookback + 1:
        return None, None
    window = valid[-(lookback + 1):]

    quantile_levels = np.array([j / states for j in range(1, states)])
    boundaries = np.quantile(window, quantile_levels)
    if len(np.unique(boundaries)) < len(boundaries):
        return None, None

    state_seq = np.digitize(window, boundaries)  # 0 .. states-1
    trans = np.zeros((states, states))
    for t in range(len(state_seq) - 1):
        trans[state_seq[t], state_seq[t + 1]] += 1

    for s in range(states):
        rs = trans[s].sum()
        if rs == 0:
            trans[s] = 1.0 / states   # no data for this state → uniform prior
        else:
            trans[s] /= rs
    return trans, int(state_seq[-1])


def markov_forecast(df, states=3, lookback=60, days_ahead=5):
    """
    Multi-step-ahead state forecast from the most recent transition matrix.

    Powers the transition matrix: the h-step distribution for the current state is
    (T^h)[current_state]. Collapsed per horizon into bull (top state) / bear
    (bottom state) probability, plus the total-variation distance from the chain's
    stationary distribution. A low-memory chain converges to stationary within a
    couple of steps — so a flattening fan (distance → 0) signals little multi-day
    edge rather than a confident forecast.

    Returns a dict:
        current_state  int | None
        states         int
        stationary     list[float]                       (length `states`)
        transition     list[list[float]]                 (the T matrix)
        horizons       list[{h, bull_prob, bear_prob, dist_to_stationary, confidence}]
    """
    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    log_ret = np.log(df["Close"] / df["Close"].shift(1)).values
    T, cur = _transition_matrix(log_ret, states, lookback)

    empty = {"current_state": None, "states": states, "stationary": [],
             "transition": [], "horizons": []}
    if T is None:
        return empty

    # stationary distribution: rows of a high power converge to it for a regular chain
    stationary = np.linalg.matrix_power(T, 256).mean(axis=0)
    s_sum = stationary.sum()
    stationary = stationary / s_sum if s_sum > 0 else np.full(states, 1.0 / states)

    def _confidence(tv):
        if tv >= 0.15:
            return "high"
        if tv >= 0.07:
            return "medium"
        if tv >= 0.03:
            return "low"
        return "~stationary"

    horizons = []
    for h in range(1, days_ahead + 1):
        dist = np.linalg.matrix_power(T, h)[cur]
        tv = 0.5 * float(np.abs(dist - stationary).sum())  # total-variation distance
        horizons.append({
            "h": h,
            "bull_prob": round(float(dist[states - 1]), 4),
            "bear_prob": round(float(dist[0]), 4),
            "dist_to_stationary": round(tv, 4),
            "confidence": _confidence(tv),
        })

    return {
        "current_state": cur,
        "states": states,
        "stationary": [round(float(x), 4) for x in stationary],
        "transition": [[round(float(x), 4) for x in row] for row in T],
        "horizons": horizons,
    }


def generate_markov_signals(mk_df, bull_threshold=0.6, bear_threshold=0.6):
    """Return a DataFrame of bars where a BUY or SELL signal fired."""
    rows = []
    for date, row in mk_df.iterrows():
        if pd.isna(row["bull_prob"]):
            continue
        if row["bull_prob"] > bull_threshold:
            rows.append({"state": row["state"], "bull_prob": round(row["bull_prob"], 3), "Signal": "BUY"})
        elif row["bear_prob"] > bear_threshold:
            rows.append({"state": row["state"], "bear_prob": round(row["bear_prob"], 3), "Signal": "SELL"})
        else:
            continue
        rows[-1]["date"] = date
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows).set_index("date")
    return result
