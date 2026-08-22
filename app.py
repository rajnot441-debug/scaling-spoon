"""
Price Action Signal Scanner
============================
A standalone Streamlit app that fetches live/historical data from Yahoo Finance
(no paid TradingView subscription needed) and detects custom candlestick /
price-action patterns:

  1. Upper Wick Rejection      -> Bearish
  2. Lower Wick Rejection      -> Bullish
  3. Equal & Symmetrical Wicks -> Volatility breakout setup
  4. Inside Bar / Range Contraction
  5. Sideways & Structural Exhaustion (3 consecutive HL/LH swings)
  6. Extreme High/Low Touch + Cross (X) markers

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Deploy free:
    Push to GitHub -> https://streamlit.io/cloud -> "New app" -> point at app.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# --------------------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="Price Action Signal Scanner", layout="wide", page_icon="📈")

# --------------------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------------------
STOCK_PRESETS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "SPY", "QQQ"]
CRYPTO_PRESETS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "BNB-USD"]
FOREX_PRESETS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X"]

# interval -> (max lookback period allowed by Yahoo, default period to request)
INTERVAL_INFO = {
    "1m":  {"max_period": "7d",   "default_period": "5d"},
    "5m":  {"max_period": "60d",  "default_period": "5d"},
    "15m": {"max_period": "60d",  "default_period": "1mo"},
    "30m": {"max_period": "60d",  "default_period": "1mo"},
    "1h":  {"max_period": "730d", "default_period": "3mo"},
    "1d":  {"max_period": "max",  "default_period": "1y"},
    "1wk": {"max_period": "max",  "default_period": "5y"},
    "1mo": {"max_period": "max",  "default_period": "10y"},
}

# --------------------------------------------------------------------------------------
# Data fetch
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_data(ticker: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.title)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index.name = "Date"
    return df


# --------------------------------------------------------------------------------------
# Pattern detection engine
# --------------------------------------------------------------------------------------
def find_pivots(values: np.ndarray, left: int, right: int, mode: str) -> np.ndarray:
    """Return boolean array marking a pivot high/low at index i if it is the
    max/min within the window [i-left, i+right]."""
    n = len(values)
    pivots = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        window = values[i - left:i + right + 1]
        center = values[i]
        if mode == "high" and center == window.max() and (window == center).sum() == 1:
            pivots[i] = True
        elif mode == "low" and center == window.min() and (window == center).sum() == 1:
            pivots[i] = True
    return pivots


def detect_signals(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    d = df.copy()
    d["Body"] = (d["Close"] - d["Open"]).abs()
    d["Range"] = (d["High"] - d["Low"]).replace(0, np.nan)
    d["UpperWick"] = d["High"] - d[["Open", "Close"]].max(axis=1)
    d["LowerWick"] = d[["Open", "Close"]].min(axis=1) - d["Low"]
    d["AvgRange"] = d["Range"].rolling(params["atr_window"], min_periods=5).mean()

    for col in ["UpperRejection", "LowerRejection", "EqualWicks", "InsideBar",
                "StructExhaustionBear", "StructExhaustionBull",
                "ExtremeHighCross", "ExtremeLowCross"]:
        d[col] = False

    body_safe = d["Body"].replace(0, 1e-9)
    range_safe = d["Range"].fillna(1e-9)

    # ---- Rule 1: Upper Wick Rejection (Bearish) --------------------------------------
    d["UpperRejection"] = (
        (d["UpperWick"] >= params["wick_body_ratio"] * body_safe)
        & (d["UpperWick"] >= params["wick_dominance"] * d["LowerWick"].replace(0, 1e-9))
        & (d["UpperWick"] >= params["min_wick_pct"] * range_safe)
    )

    # ---- Rule 2: Lower Wick Rejection (Bullish) --------------------------------------
    d["LowerRejection"] = (
        (d["LowerWick"] >= params["wick_body_ratio"] * body_safe)
        & (d["LowerWick"] >= params["wick_dominance"] * d["UpperWick"].replace(0, 1e-9))
        & (d["LowerWick"] >= params["min_wick_pct"] * range_safe)
    )

    # ---- Rule 3: Equal & Symmetrical Wicks (volatility breakout setup) ---------------
    both_sizable = (d["UpperWick"] >= params["min_wick_pct"] * range_safe) & \
                   (d["LowerWick"] >= params["min_wick_pct"] * range_safe)
    symmetrical = (d["UpperWick"] - d["LowerWick"]).abs() <= params["symmetry_tol"] * range_safe
    small_body = d["Body"] <= params["indecision_body_pct"] * range_safe
    d["EqualWicks"] = both_sizable & symmetrical & small_body

    # ---- Rule 4: Inside Bar / Range Contraction --------------------------------------
    prev_high = d["High"].shift(1)
    prev_low = d["Low"].shift(1)
    d["InsideBar"] = (d["High"] <= prev_high) & (d["Low"] >= prev_low)

    # ---- Rule 5: Sideways & Structural Exhaustion ------------------------------------
    left = right = params["pivot_span"]
    highs = d["High"].to_numpy()
    lows = d["Low"].to_numpy()
    pivot_high_mask = find_pivots(highs, left, right, "high")
    pivot_low_mask = find_pivots(lows, left, right, "low")

    piv_high_idx = np.where(pivot_high_mask)[0]
    piv_low_idx = np.where(pivot_low_mask)[0]

    small_body_flag = (d["Body"] <= params["small_body_pct"] * d["AvgRange"]).to_numpy()

    # 3 consecutive lower highs -> sideways/topping exhaustion -> bearish reversal flag
    for k in range(2, len(piv_high_idx)):
        i0, i1, i2 = piv_high_idx[k - 2], piv_high_idx[k - 1], piv_high_idx[k]
        if highs[i0] > highs[i1] > highs[i2]:
            window_small = small_body_flag[max(0, i0 - 1):i2 + 1]
            if window_small.size and window_small.mean() >= params["small_body_frac"]:
                d.iloc[i2, d.columns.get_loc("StructExhaustionBear")] = True

    # 3 consecutive higher lows -> sideways/bottoming exhaustion -> bullish reversal flag
    for k in range(2, len(piv_low_idx)):
        i0, i1, i2 = piv_low_idx[k - 2], piv_low_idx[k - 1], piv_low_idx[k]
        if lows[i0] < lows[i1] < lows[i2]:
            window_small = small_body_flag[max(0, i0 - 1):i2 + 1]
            if window_small.size and window_small.mean() >= params["small_body_frac"]:
                d.iloc[i2, d.columns.get_loc("StructExhaustionBull")] = True

    # ---- Rule 6: Extreme High/Low Touch & Cross Signals ------------------------------
    roll_max = d["High"].rolling(params["extreme_window"], min_periods=5).max()
    roll_min = d["Low"].rolling(params["extreme_window"], min_periods=5).min()

    d["ExtremeHighCross"] = (d["High"] >= roll_max) & d["UpperRejection"]
    d["ExtremeLowCross"] = (d["Low"] <= roll_min) & d["LowerRejection"]

    return d


# --------------------------------------------------------------------------------------
# Chart builder
# --------------------------------------------------------------------------------------
def build_chart(d: pd.DataFrame, ticker: str, interval: str) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
        name=ticker, increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ))

    marker_specs = [
        ("UpperRejection", d["High"] * 1.003, "triangle-down", "#ef5350", "Upper Wick Rejection (Bearish)"),
        ("LowerRejection", d["Low"] * 0.997, "triangle-up", "#26a69a", "Lower Wick Rejection (Bullish)"),
        ("EqualWicks", d["High"] * 1.006, "diamond", "#fbc02d", "Equal/Symmetrical Wicks (Breakout Setup)"),
        ("InsideBar", (d["High"] + d["Low"]) / 2, "square", "#42a5f5", "Inside Bar / Contraction"),
        ("StructExhaustionBear", d["High"] * 1.009, "star", "#ab47bc", "Structural Exhaustion (Bearish)"),
        ("StructExhaustionBull", d["Low"] * 0.994, "star", "#7e57c2", "Structural Exhaustion (Bullish)"),
    ]

    for col, ypos, symbol, color, label in marker_specs:
        mask = d[col]
        if mask.any():
            fig.add_trace(go.Scatter(
                x=d.index[mask], y=ypos[mask], mode="markers", name=label,
                marker=dict(symbol=symbol, size=10, color=color, line=dict(width=1, color="black")),
            ))

    # Extreme touch cross (X) markers - larger, distinct
    extreme_bear = d["ExtremeHighCross"]
    extreme_bull = d["ExtremeLowCross"]
    if extreme_bear.any():
        fig.add_trace(go.Scatter(
            x=d.index[extreme_bear], y=d["High"][extreme_bear] * 1.012, mode="markers",
            name="Extreme High Touch (X - Reversal Down)",
            marker=dict(symbol="x", size=15, color="black", line=dict(width=2, color="#ef5350")),
        ))
    if extreme_bull.any():
        fig.add_trace(go.Scatter(
            x=d.index[extreme_bull], y=d["Low"][extreme_bull] * 0.988, mode="markers",
            name="Extreme Low Touch (X - Reversal Up)",
            marker=dict(symbol="x", size=15, color="black", line=dict(width=2, color="#26a69a")),
        ))

    fig.update_layout(
        title=f"{ticker} — {interval} chart",
        xaxis_rangeslider_visible=False,
        height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=60, b=10),
        template="plotly_white",
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])] if interval in ("1m", "5m", "15m", "30m", "1h") else None)
    return fig


# --------------------------------------------------------------------------------------
# Sidebar UI
# --------------------------------------------------------------------------------------
st.sidebar.title("📈 Signal Scanner Settings")

asset_class = st.sidebar.radio("Asset Class", ["Stocks", "Crypto", "Forex", "Custom"], horizontal=False)

if asset_class == "Stocks":
    ticker = st.sidebar.selectbox("Ticker", STOCK_PRESETS)
elif asset_class == "Crypto":
    ticker = st.sidebar.selectbox("Ticker", CRYPTO_PRESETS)
elif asset_class == "Forex":
    ticker = st.sidebar.selectbox("Pair", FOREX_PRESETS)
else:
    ticker = st.sidebar.text_input("Custom Yahoo Finance Ticker", value="AAPL").strip()

interval = st.sidebar.selectbox("Timeframe", list(INTERVAL_INFO.keys()), index=5)
default_period = INTERVAL_INFO[interval]["default_period"]
period = st.sidebar.text_input("Lookback Period (yfinance format, e.g. 5d, 1mo, 1y)", value=default_period)

st.sidebar.markdown("---")
st.sidebar.subheader("Pattern Sensitivity")

with st.sidebar.expander("Wick Rejection Rules (1 & 2)", expanded=False):
    wick_body_ratio = st.slider("Wick must be ≥ X × body", 1.0, 5.0, 2.0, 0.1)
    wick_dominance = st.slider("Dominant wick ≥ X × opposite wick", 1.0, 5.0, 2.0, 0.1)
    min_wick_pct = st.slider("Min wick size (% of candle range)", 0.1, 0.9, 0.35, 0.05)

with st.sidebar.expander("Equal/Symmetrical Wicks (Rule 3)", expanded=False):
    symmetry_tol = st.slider("Max wick imbalance (% of range)", 0.02, 0.3, 0.1, 0.01)
    indecision_body_pct = st.slider("Max body size (% of range)", 0.1, 0.6, 0.3, 0.05)

with st.sidebar.expander("Structural Exhaustion (Rule 5)", expanded=False):
    pivot_span = st.slider("Pivot detection span (bars each side)", 1, 5, 2)
    small_body_pct = st.slider("'Small candle' threshold (× avg range)", 0.2, 1.0, 0.6, 0.05)
    small_body_frac = st.slider("Min fraction of small candles in swing", 0.2, 1.0, 0.5, 0.05)
    atr_window = st.slider("Average range window (bars)", 5, 50, 14)

with st.sidebar.expander("Extreme Touch (Rule 6)", expanded=False):
    extreme_window = st.slider("Local extreme lookback window (bars)", 5, 100, 20)

lookback_display = st.sidebar.slider("Show last N bars", 30, 500, 150, 10)

refresh = st.sidebar.button("🔄 Refresh Data")
if refresh:
    st.cache_data.clear()

params = dict(
    wick_body_ratio=wick_body_ratio, wick_dominance=wick_dominance, min_wick_pct=min_wick_pct,
    symmetry_tol=symmetry_tol, indecision_body_pct=indecision_body_pct,
    pivot_span=pivot_span, small_body_pct=small_body_pct, small_body_frac=small_body_frac,
    atr_window=atr_window, extreme_window=extreme_window,
)

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
st.title("Price Action & Candlestick Signal Scanner")
st.caption("Free, self-contained tool — pulls data from Yahoo Finance. No TradingView subscription required.")

if not ticker:
    st.warning("Enter a ticker to begin.")
    st.stop()

with st.spinner(f"Fetching {ticker} ({interval}, {period})..."):
    raw = fetch_data(ticker, interval, period)

if raw.empty:
    st.error("No data returned. Try a different ticker/timeframe/period (intraday intervals have limited history on Yahoo Finance).")
    st.stop()

signals_df = detect_signals(raw, params)
view = signals_df.tail(lookback_display)

col_chart, col_panel = st.columns([3, 1])

with col_chart:
    fig = build_chart(view, ticker, interval)
    st.plotly_chart(fig, use_container_width=True)

with col_panel:
    st.subheader("⚡ Live Signal Panel")
    last_row = signals_df.iloc[-1]
    last_time = signals_df.index[-1]

    active = []
    if last_row["UpperRejection"]:
        active.append(("🔴 Upper Wick Rejection", "Bearish"))
    if last_row["LowerRejection"]:
        active.append(("🟢 Lower Wick Rejection", "Bullish"))
    if last_row["EqualWicks"]:
        active.append(("🟡 Equal/Symmetrical Wicks", "Volatility Breakout Watch"))
    if last_row["InsideBar"]:
        active.append(("🔵 Inside Bar", "Range Contraction"))
    if last_row["StructExhaustionBear"]:
        active.append(("🟣 Structural Exhaustion", "Bearish Reversal Setup"))
    if last_row["StructExhaustionBull"]:
        active.append(("🟣 Structural Exhaustion", "Bullish Reversal Setup"))
    if last_row["ExtremeHighCross"]:
        active.append(("❌ Extreme High Touch", "Reversal Down Signal"))
    if last_row["ExtremeLowCross"]:
        active.append(("❌ Extreme Low Touch", "Reversal Up Signal"))

    if active:
        for name, meaning in active:
            st.success(f"**{name}**\n\n{meaning}")
    else:
        st.info("No signals on the most recent candle.")

    st.caption(f"Last bar: {last_time}")
    st.metric("Last Close", f"{last_row['Close']:.5f}" if last_row['Close'] < 5 else f"{last_row['Close']:.2f}")

st.markdown("---")
st.subheader("📋 Recent Signal History")

signal_cols = {
    "UpperRejection": "Upper Wick Rejection (Bearish)",
    "LowerRejection": "Lower Wick Rejection (Bullish)",
    "EqualWicks": "Equal/Symmetrical Wicks",
    "InsideBar": "Inside Bar",
    "StructExhaustionBear": "Structural Exhaustion (Bearish)",
    "StructExhaustionBull": "Structural Exhaustion (Bullish)",
    "ExtremeHighCross": "Extreme High Touch (X)",
    "ExtremeLowCross": "Extreme Low Touch (X)",
}

rows = []
for col, label in signal_cols.items():
    hits = view[view[col]]
    for ts, r in hits.iterrows():
        rows.append({"Time": ts, "Signal": label, "Close": round(r["Close"], 5)})

if rows:
    hist_df = pd.DataFrame(rows).sort_values("Time", ascending=False).reset_index(drop=True)
    st.dataframe(hist_df, use_container_width=True, height=350)
else:
    st.info("No signals detected in the displayed window. Try loosening sensitivity settings in the sidebar.")

with st.expander("ℹ️ Rule Definitions"):
    st.markdown("""
- **Upper Wick Rejection (Bearish):** Long upper wick dominates the candle, suggesting sellers rejected higher prices.
- **Lower Wick Rejection (Bullish):** Long lower wick dominates the candle, suggesting buyers rejected lower prices.
- **Equal & Symmetrical Wicks:** Both wicks are large and roughly equal with a small body — indecision that often precedes a high-volatility breakout.
- **Inside Bar / Range Contraction:** Current candle's high/low sits fully inside the prior candle's range — coiling before an explosive move.
- **Sideways & Structural Exhaustion:** Three consecutive lower highs (or higher lows) formed by small-bodied candles, indicating fading momentum before a possible reversal.
- **Extreme High/Low Touch & Cross (X):** Price touches a local rolling extreme *and* shows a strong wick rejection at that level — plotted as an X marker on the chart.

All thresholds are adjustable in the sidebar under **Pattern Sensitivity**.
""")

st.caption("Data: Yahoo Finance via yfinance. For informational purposes only — not financial advice.")
