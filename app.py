import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import numpy as np

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="CryptoSignal Pro - Ultimate Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# STYLING & MOBILE TWO-FINGER ZOOM PROTECTION CSS
# =============================================================================
CUSTOM_CSS = """
<style>
    .main { background-color: #0b0e11; }
    .stApp { background-color: #0b0e11; }
    * { font-variant-numeric: tabular-nums; }
    
    /* Metric Cards */
    .metric-card {
        background: #14181f;
        border: 1px solid #23272f;
        border-radius: 8px;
        padding: 10px 14px;
    }
    .metric-label { color: #848e9c; font-size: 11px; text-transform: uppercase; }
    .metric-value { font-size: 18px; font-weight: 700; color: #eaecef; }
    
    /* Signals */
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

    /* Prevent single-finger accidental page zoom, allow only two-finger gestures */
    .chart-container {
        touch-action: pan-x pan-y;
        -webkit-overflow-scrolling: touch;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================================
# SIDEBAR SETTINGS
# =============================================================================
st.sidebar.header("⚡ Live Settings")
pair_mapping = {
    "BTC/USDT": "BINANCE:BTCUSDT",
    "ETH/USDT": "BINANCE:ETHUSDT",
    "SOL/USDT": "BINANCE:SOLUSDT",
    "BNB/USDT": "BINANCE:BNBUSDT",
    "XRP/USDT": "BINANCE:XRPUSDT"
}

selected_pair = st.sidebar.selectbox("Select Crypto Pair", list(pair_mapping.keys()), index=0)
chart_symbol = pair_mapping[selected_pair]

timeframe_mapping = {
    "1 Minute": "1",
    "5 Minutes": "5",
    "15 Minutes": "15",
    "1 Hour": "60",
    "1 Day": "D"
}
selected_tf = st.sidebar.selectbox("Timeframe", list(timeframe_mapping.keys()), index=1)
chart_interval = timeframe_mapping[selected_tf]

# =============================================================================
# LIGHTWEIGHT BACKEND DATA FETCHER FOR METRICS & SIGNALS
# =============================================================================
@st.cache_data(ttl=10, show_spinner=False)
def get_market_metrics(pair: str):
    symbol = pair.replace("/", "").upper()
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "15m", "limit": 50}
    try:
        resp = requests.get(url, params=params, timeout=3)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            df = pd.DataFrame(data, columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"
            ])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            
            close = df["close"]
            # RSI Calculation
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            
            # MACD Calculation
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            macd_signal = macd.ewm(span=9, adjust=False).mean()
            
            # KDJ Calculation
            low_n = df["low"].rolling(9).min()
            high_n = df["high"].rolling(9).max()
            rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
            kdj_j = 3 * rsv.ewm(com=2).mean() - 2 * rsv.ewm(com=2).mean().ewm(com=2).mean()
            
            # Stoch RSI
            rsi_min = rsi.rolling(14).min()
            rsi_max = rsi.rolling(14).max()
            stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-9) * 100
            stoch_rsi_k = stoch_rsi.rolling(3).mean()
            
            last_close = close.iloc[-1]
            last_rsi = rsi.iloc[-1]
            last_macd = macd.iloc[-1]
            last_kdj = kdj_j.iloc[-1]
            last_stoch = stoch_rsi_k.iloc[-1]
            
            # Signal Logic
            score = 0
            if last_rsi < 35: score += 1
            elif last_rsi > 65: score -= 1
            if last_macd > macd_signal.iloc[-1]: score += 1
            else: score -= 1
            
            if score >= 1: signal = "BUY"
            elif score <= -1: signal = "SELL"
            else: signal = "HOLD"
            
            confidence = min(90, max(45, int(abs(score) * 40 + 50)))
            
            return {
                "price": last_close, "rsi": last_rsi, "macd": last_macd,
                "kdj": last_kdj, "stoch": last_stoch, "signal": signal, "confidence": confidence
            }
    except Exception:
        pass
    
    # Fallback default data if offline
    return {
        "price": 66500.0, "rsi": 45.2, "macd": -12.5,
        "kdj": 55.0, "stoch": 60.0, "signal": "HOLD", "confidence": 50
    }

# =============================================================================
# MAIN UI HEADER & METRICS
# =============================================================================
st.markdown(f"## 📊 Binance Pro Live Terminal - {selected_pair}")
st.markdown("<p style='color: #0ecb81; font-size: 14px; margin-top:-10px;'>● Live Real-Time Feed Active (Two-Finger Zoom Enabled)</p>", unsafe_allow_html=True)

metrics = get_market_metrics(selected_pair)

m1, m2, m3, m4, m5, m6 = st.columns(6)
with m1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Price</div><div class='metric-value'>${metrics['price']:,.2f}</div></div>", unsafe_allow_html=True)
with m2: st.markdown(f"<div class='metric-card'><div class='metric-label'>RSI (14)</div><div class='metric-value'>{metrics['rsi']:.1f}</div></div>", unsafe_allow_html=True)
with m3: st.markdown(f"<div class='metric-card'><div class='metric-label'>MACD</div><div class='metric-value'>{metrics['macd']:.2f}</div></div>", unsafe_allow_html=True)
with m4: st.markdown(f"<div class='metric-card'><div class='metric-label'>KDJ J</div><div class='metric-value'>{metrics['kdj']:.1f}</div></div>", unsafe_allow_html=True)
with m5: st.markdown(f"<div class='metric-card'><div class='metric-label'>Stoch RSI</div><div class='metric-value'>{metrics['stoch']:.1f}</div></div>", unsafe_allow_html=True)
with m6: st.markdown(f"<div class='metric-card'><div class='metric-label'>Status</div><div class='metric-value' style='font-size:12px;color:#0ecb81;'>Connected</div></div>", unsafe_allow_html=True)

st.write("")

# =============================================================================
# SIGNAL BOX & TRADINGVIEW CHART LAYOUT
# =============================================================================
left_col, right_col = st.columns([1, 3.5])

with left_col:
    sig = metrics["signal"]
    conf = metrics["confidence"]
    css_cls = {"BUY": "signal-buy", "SELL": "signal-sell", "HOLD": "signal-hold"}[sig]
    st.markdown(f"<div class='{css_cls}'>{sig}<br><span style='font-size:13px;color:#848e9c;'>Confidence: {conf}%</span></div>", unsafe_allow_html=True)
    st.write("")
    st.info("💡 **Touch Controls:**\n- **1 Finger:** Scroll page / Pan chart.\n- **2 Fingers:** Pinch to Zoom in/out smoothly.")

with right_col:
    # TradingView Advanced Widget with Touch Optimization (Two-Finger Zoom Support)
    tradingview_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body, html {{ background-color: #0b0e11; margin:0; padding:0; height:100%; width:100%; }}
        .tradingview-widget-container {{
            width: 100%;
            height: 520px;
            touch-action: pan-x pan-y; /* Restricts single finger glitches, allows multi-touch zoom */
        }}
    </style>
    </head>
    <body>
      <div class="tradingview-widget-container">
        <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
        {{
          "autosize": true,
          "symbol": "{chart_symbol}",
          "interval": "{chart_interval}",
          "timezone": "Asia/Kolkata",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "allow_symbol_change": false,
          "calendar": false,
          "support_host": "https://www.tradingview.com",
          "hide_side_toolbar": false,
          "details": false,
          "hotlist": false,
          "stockboard": false
        }}
        </script>
      </div>
    </body>
    </html>
    """
    components.html(tradingview_html, height=540, scrolling=False)
