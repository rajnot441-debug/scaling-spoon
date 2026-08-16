import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# =============================================================================
# PAGE CONFIG & 1-SECOND AUTO REFRESH
# =============================================================================
st.set_page_config(
    page_title="CryptoSignal Pro - Live Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 1 Second Live Auto-Refresh (1000 milliseconds)
st_autorefresh(interval=1000, key="live_crypto_ticker")

# =============================================================================
# STYLING (Binance Pro Dark Theme)
# =============================================================================
CUSTOM_CSS = """
<style>
    .main { background-color: #0b0e11; }
    * { font-variant-numeric: tabular-nums; }
    .metric-card {
        background: #14181f;
        border: 1px solid #23272f;
        border-radius: 8px;
        padding: 10px 14px;
    }
    .metric-label { color: #848e9c; font-size: 11px; text-transform: uppercase; }
    .metric-value { font-size: 18px; font-weight: 700; color: #eaecef; }
    .signal-buy {
        background: #0d1f17; border: 1px solid #0ecb81; border-radius: 8px;
        padding: 15px; text-align: center; font-size: 22px; font-weight: 800; color: #0ecb81;
    }
    .signal-sell {
        background: #23131a; border: 1px solid #f6465d; border-radius: 8px;
        padding: 15px; text-align: center; font-size: 22px; font-weight: 800; color: #f6465d;
    }
    .signal-hold {
        background: #241f10; border: 1px solid #f0b90b; border-radius: 8px;
        padding: 15px; text-align: center; font-size: 22px; font-weight: 800; color: #f0b90b;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================================
# YAHOO FINANCE CLOUD-SAFE LIVE DATA FETCHER
# =============================================================================
@st.cache_data(ttl=5, show_spinner=False)
def fetch_live_data(pair: str, timeframe: str):
    symbol_map = {
        "BTC/USDT": "BTC-USD",
        "ETH/USDT": "ETH-USD",
        "SOL/USDT": "SOL-USD",
        "BNB/USDT": "BNB-USD"
    }
    ticker = symbol_map.get(pair, "BTC-USD")
    
    tf_map = {
        "1m": ("1d", "1m"),
        "5m": ("5d", "5m"),
        "15m": ("5d", "15m"),
        "1h": ("1mo", "1h")
    }
    period, interval = tf_map.get(timeframe, ("1d", "5m"))
    
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.columns = ["open", "high", "low", "close", "volume"]
            return df, "Yahoo Finance Live"
    except Exception:
        pass
        
    return pd.DataFrame(), "Error"

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df
    df["ma_20"] = df["close"].rolling(20).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    
    std = df["close"].rolling(20).std()
    df["bb_upper"] = df["ma_20"] + (2.0 * std)
    df["bb_lower"] = df["ma_20"] - (2.0 * std)
    
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    
    rsi_min = df["rsi"].rolling(14).min()
    rsi_max = df["rsi"].rolling(14).max()
    stoch_rsi = (df["rsi"] - rsi_min) / (rsi_max - rsi_min + 1e-9) * 100
    df["stoch_rsi_k"] = stoch_rsi.rolling(3).mean()
    
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    
    low_n = df["low"].rolling(9).min()
    high_n = df["high"].rolling(9).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    df["kdj_j"] = 3 * rsv.ewm(com=2).mean() - 2 * rsv.ewm(com=2).mean().ewm(com=2).mean()
    
    return df

def generate_signals(df: pd.DataFrame):
    if df.empty or len(df) < 5:
        return "HOLD", 50, {}
    last = df.iloc[-1]
    score = 0
    
    if last["close"] > last.get("ema_50", last["close"]): score += 1
    else: score -= 1
    
    rsi_val = last.get("rsi", 50)
    if pd.notna(rsi_val):
        if rsi_val < 30: score += 1
        elif rsi_val > 70: score -= 1
        
    macd_val = last.get("macd", 0)
    macd_sig = last.get("macd_signal", 0)
    if pd.notna(macd_val) and pd.notna(macd_sig):
        if macd_val > macd_sig: score += 1
        else: score -= 1
    
    if score >= 2: signal = "BUY"
    elif score <= -2: signal = "SELL"
    else: signal = "HOLD"
    
    confidence = min(95, max(40, int(abs(score) / 3 * 80 + 20)))
    return signal, confidence, last

# =============================================================================
# MAIN INTERFACE
# =============================================================================
st.sidebar.header("⚡ Live Settings")
pair = st.sidebar.selectbox("Pair", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], index=0)
timeframe = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h"], index=1)

st.markdown("## 📊 Pro Live Trading Terminal (Yahoo Feed)")

try:
    raw_df, source = fetch_live_data(pair, timeframe)
    
    if raw_df is None or raw_df.empty:
        st.warning("⚠️ மார்க்கெட் டேட்டா கிடைப்பதில் சிறு தாமதம்... அடுத்த விநாடியில் சரியாகிவிடும்.")
        st.stop()
        
    df = compute_all_indicators(raw_df)
    
    if df.empty or len(df) < 10:
        st.warning("⚠️ போதுமான கேண்டில் டேட்டா கிடைக்கவில்லை...")
        st.stop()
        
    signal, confidence, last = generate_signals(df)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Price</div><div class='metric-value'>${last['close']:,.2f}</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-card'><div class='metric-label'>RSI (14)</div><div class='metric-value'>{last.get('rsi', 0):.1f}</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-card'><div class='metric-label'>MACD</div><div class='metric-value'>{last.get('macd', 0):.2f}</div></div>", unsafe_allow_html=True)
    with m4: st.markdown(f"<div class='metric-card'><div class='metric-label'>KDJ J</div><div class='metric-value'>{last.get('kdj_j', 0):.1f}</div></div>", unsafe_allow_html=True)
    with m5: st.markdown(f"<div class='metric-card'><div class='metric-label'>Stoch RSI</div><div class='metric-value'>{last.get('stoch_rsi_k', 0):.1f}</div></div>", unsafe_allow_html=True)
    with m6: st.markdown(f"<div class='metric-card'><div class='metric-label'>Source</div><div class='metric-value' style='font-size:12px;color:#0ecb81;'>{source}</div></div>", unsafe_allow_html=True)

    st.write("")

    left_col, right_col = st.columns([1, 3.2])

    with left_col:
        css_cls = {"BUY": "signal-buy", "SELL": "signal-sell", "HOLD": "signal-hold"}[signal]
        st.markdown(f"<div class='{css_cls}'>{signal}<br><span style='font-size:13px;color:#848e9c;'>Confidence: {confidence}%</span></div>", unsafe_allow_html=True)
        st.write("")
        st.info("💡 **Live Terminal Active:**\n- Yahoo Finance Enterprise Feed.\n- 100% Cloud-Safe & No Blocking.\n- Clean Binance Pro UI.")

    with right_col:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df.get("bb_upper"), name="BB Upper", line=dict(color="rgba(100,150,255,0.3)", width=1), hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=df.index, y=df.get("bb_lower"), name="BB Lower", line=dict(color="rgba(100,150,255,0.3)", width=1), fill='tonexty', fillcolor='rgba(100,150,255,0.05)', hoverinfo='skip'))

        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="Price", increasing_line_color="#0ecb81", decreasing_line_color="#f6465d"
        ))

        fig.add_trace(go.Scatter(x=df.index, y=df.get("ma_20"), name="MA 20", line=dict(color="#f0b90b", width=1.2)))
        fig.add_trace(go.Scatter(x=df.index, y=df.get("ema_20"), name="EMA 20", line=dict(color="#3498db", width=1.2)))
        fig.add_trace(go.Scatter(x=df.index, y=df.get("ema_50"), name="EMA 50", line=dict(color="#9b59b6", width=1.5)))

        fig.update_layout(
            height=500,
            template="plotly_dark",
            paper_bgcolor="#0b0e11",
            plot_bgcolor="#0b0e11",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        chart_config = {
            "scrollZoom": True,
            "displayModeBar": False,
            "doubleClick": "reset"
        }

        st.plotly_chart(fig, use_container_width=True, config=chart_config)

except Exception as e:
    st.error(f"Live Terminal Error: {e}")
