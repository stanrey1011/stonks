import pandas as pd
import plotly.graph_objects as go

def overlay_trace(fig, file_path, df, interval, name_fmt=None, dash=None, row=1, col=1):
    if file_path.exists():
        data = pd.read_csv(file_path, index_col=0, parse_dates=True)
        if interval in ["1m","2m","5m","15m","30m","1h"]:
            if getattr(data.index, "tz", None) is None:
                data.index = pd.to_datetime(data.index, utc=True).tz_convert('US/Eastern')
            else:
                data.index = data.index.tz_convert('US/Eastern')
        else:
            if getattr(data.index, "tz", None) is None:
                data.index = pd.to_datetime(data.index, utc=True)
            else:
                data.index = data.index.tz_convert('UTC')
        data = data.reindex(df.index)
        x_overlay = data.index
        for colname in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=x_overlay,
                    y=data[colname],
                    mode="lines",
                    name=name_fmt.format(col=colname) if name_fmt else colname,
                    line=dict(width=1, dash=dash) if dash else dict(width=1)
                ),
                row=row, col=col
            )
