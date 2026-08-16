"""
CryptoSignal Pro — Multi-Exchange Technical Analysis Terminal
----------------------------------------------------------------
A Streamlit dashboard, styled after the dark, dense, data-forward layout
common to professional crypto exchange terminals (candlesticks, a compact
order book, an indicator stack, and a signal readout). It is an original
UI built in that general style — not a pixel copy of any specific
exchange's proprietary interface, logo, or trademark.

Live OHLCV comes from CCXT across several exchanges, with a CoinGecko
public-API fallback if every exchange attempt fails (e.g. cloud-host
geo-blocking). Includes a simulated login/auth flow and a Free vs
Premium Pro tier gate with a placeholder payment hook.

STRICTLY ANALYSIS ONLY: no order execution, no wallet/deposit/withdrawal
features, no real-money trading of any kind.

⚠️ EDUCATIONAL USE ONLY — NOT FINANCIAL ADVICE. See in-app disclaimer.
"""

import time
import hashlib
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

try:
    import ccxt
except ImportError:
    ccxt = None


# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="CryptoSignal Pro | Multi-Exchange TA Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# LIVE AUTO-REFRESH ENGINE (Makes the app live every 5 seconds)
st_autorefresh(interval=5000, key="live_crypto_ticker")

# =============================================================================
# CONSTANTS
# =============================================================================
EXCHANGES = ["binance", "coinbase", "kraken", "kucoin", "bybit", "okx", "gateio"]
FREE_EXCHANGES = ["binance", "kraken"]

FALLBACK_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
    "LINK/USDT", "MATIC/USDT",
]
FREE_PAIRS = ["BTC/USDT", "ETH/USDT"]

TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
FREE_TIMEFRAMES = ["1h", "4h", "1d"]
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

CCXT_FALLBACK_ORDER = ["binance", "kucoin", "bybit", "okx", "gateio", "kraken", "coinbase"]

COINGECKO_ID_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "LINK": "chainlink", "MATIC": "matic-network",
}
TF_TO_CG_DAYS = {"5m": 1, "15m": 1, "1h": 30, "4h": 90, "1d": 365}
TF_TO_RESAMPLE_RULE = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}

DEMO_USERS = {
    "demo": {"password": "demo123", "tier": "Free"},
    "pro": {"password": "pro123", "tier": "Premium Pro"},
}

# =============================================================================
# STYLE
# =============================================================================
CUSTOM_CSS = """
<style>
    .main { background-color: #0b0e11; }
    * { font-variant-numeric: tabular-nums; }
    .metric-card {
        background: #14181f;
        border: 1px solid #23272f;
        border-radius: 10px;
        padding: 14px 16px;
    }
    .metric-label { color: #848e9c; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .metric-value { font-size: 21px; font-weight: 700; color: #eaecef; }
    .signal-buy {
        background: #0d1f17; border: 1px solid #0ecb81; border-radius: 10px;
        padding: 20px; text-align: center; font-size: 26px; font-weight: 800; color: #0ecb81;
    }
    .signal-sell {
        background: #23131a; border: 1px solid #f6465d; border-radius: 10px;
        padding: 20px; text-align: center; font-size: 26px; font-weight: 800; color: #f6465d;
    }
    .signal-hold {
        background: #241f10; border: 1px solid #f0b90b; border-radius: 10px;
        padding: 20px; text-align: center; font-size: 26px; font-weight: 800; color: #f0b90b;
    }
    .premium-badge {
        background: linear-gradient(90deg, #f0b90b, #f8d33a); color: #1a1a1a;
        padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700;
    }
    .free-badge {
        background: #23272f; color: #848e9c; padding: 2px 9px; border-radius: 20px;
        font-size: 11px; font-weight: 700;
    }
    .lock-badge {
        background: #23272f; color: #5b6472; padding: 1px 7px; border-radius: 10px; font-size: 10px;
    }
    .ob-row { display:flex; justify-content:space-between; font-size:12.5px; padding:1px 4px; font-family: monospace; }
    .ob-ask { color:#f6465d; }
    .ob-bid { color:#0ecb81; }
    .disclaimer-box {
        background-color: #14181f; border-left: 4px solid #f6465d;
        padding: 14px 18px; border-radius: 6px; font-size: 13px; color: #b7bdc6;
    }
    section[data-testid="stSidebar"] { background-color: #0e1116; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE
# =============================================================================
def init_state():
    defaults = {"logged_in": False, "username": None, "tier": "Free", "show_upgrade": False}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# =============================================================================
# AUTH SCREEN
# =============================================================================
def login_screen():
    st.markdown("<h1 style='text-align:center;'>📊 CryptoSignal Pro</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center;color:#848e9c;'>Multi-exchange technical analysis terminal — signals, not trades</p>",
        unsafe_allow_html=True,
    )
    st.write("")

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container(border=True):
            tab_login, tab_signup = st.tabs(["Login", "Create Account"])
            with tab_login:
                st.caption("Demo accounts: `demo` / `demo123` (Free) or `pro` / `pro123` (Premium)")
                u = st.text_input("Username", key="login_user")
                p = st.text_input("Password", type="password", key="login_pass")
                if st.button("Log In", use_container_width=True, type="primary"):
                    record = DEMO_USERS.get(u)
                    if record and record["password"] == p:
                        st.session_state.logged_in = True
                        st.session_state.username = u
                        st.session_state.tier = record["tier"]
                        st.success(f"Welcome back, {u}!")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
            with tab_signup:
                st.caption("Simulated sign-up for demo purposes only.")
                new_user = st.text_input("Choose a username", key="signup_user")
                new_pass = st.text_input("Choose a password", type="password", key="signup_pass")
                if st.button("Create Free Account", use_container_width=True):
                    if new_user and new_pass:
                        DEMO_USERS[new_user] = {"password": new_pass, "tier": "Free"}
                        st.success("Account created! Please log in with the Login tab.")
                    else:
                        st.warning("Enter a username and password.")

    st.markdown(
        """
        <div class='disclaimer-box' style='margin-top:30px;'>
        ⚠️ <b>Risk Disclaimer:</b> Educational/informational tool only — not financial advice.
        This login is simulated, not production authentication. This platform never executes
        trades, holds funds, or touches a wallet. Crypto trading carries substantial risk of loss;
        always do your own research and consult a licensed advisor.
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# MARKET / DATA LOADING
# =============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_markets_for_exchange(exchange_id: str):
    if ccxt is None:
        return []
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({"enableRateLimit": True, "timeout": 8000})
        markets = exchange.load_markets()
        symbols = [
            s for s, m in markets.items()
            if m.get("active", True) and m.get("spot", True) and "/" in s
            and s.split("/")[-1] in ("USDT", "USD", "USDC")
        ]
        return sorted(set(symbols))
    except Exception:
        return []


def _fetch_ohlcv_ccxt(pair: str, timeframe: str, limit: int, exchange_id: str) -> pd.DataFrame:
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True, "timeout": 8000})
    raw = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
    if not raw:
        raise ValueError("empty OHLCV response")
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def _fetch_ohlcv_coingecko(pair: str, timeframe: str, limit: int) -> pd.DataFrame:
    base = pair.split("/")[0].upper()
    coin_id = COINGECKO_ID_MAP.get(base)
    if not coin_id:
        raise ValueError(f"No CoinGecko mapping for base asset '{base}'")

    days = TF_TO_CG_DAYS.get(timeframe, 30)
    rule = TF_TO_RESAMPLE_RULE.get(timeframe, "1h")

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    resp = requests.get(url, params={"vs_currency": "usd", "days": days}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()

    prices = payload.get("prices", [])
    volumes = payload.get("total_volumes", [])
    if not prices:
        raise ValueError("CoinGecko returned no price data")

    price_df = pd.DataFrame(prices, columns=["ts", "price"])
    price_df["ts"] = pd.to_datetime(price_df["ts"], unit="ms")
    price_df.set_index("ts", inplace=True)

    vol_df = pd.DataFrame(volumes, columns=["ts", "volume"])
    vol_df["ts"] = pd.to_datetime(vol_df["ts"], unit="ms")
    vol_df.set_index("ts", inplace=True)

    ohlc = price_df["price"].resample(rule).ohlc()
    vol = vol_df["volume"].resample(rule).mean()

    df = ohlc.join(vol, how="left")
    df["volume"] = df["volume"].fillna(method="ffill")
    df.dropna(subset=["open", "high", "low", "close"], inplace=True)
    if df.empty:
        raise ValueError("Resampled CoinGecko data is empty")
    return df.tail(limit)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(pair: str, timeframe: str, preferred_exchange: str, limit: int = 300):
    errors = []
    try_order = [preferred_exchange] + [e for e in CCXT_FALLBACK_ORDER if e != preferred_exchange]

    if ccxt is not None:
        for exchange_id in try_order:
            try:
                df = _fetch_ohlcv_ccxt(pair, timeframe, limit, exchange_id)
                label = f"{exchange_id} (via CCXT)"
                if exchange_id != preferred_exchange:
                    label += f" — {preferred_exchange} was unavailable"
                return df, label
            except Exception as e:
                errors.append(f"{exchange_id}: {e}")
                continue
    else:
        errors.append("ccxt not installed")

    try:
        df = _fetch_ohlcv_coingecko(pair, timeframe, limit)
        return df, "CoinGecko (public API fallback — approximate volume)"
    except Exception as e:
        errors.append(f"coingecko: {e}")

    raise RuntimeError("All data providers failed:\n- " + "\n- ".join(errors))


@st.cache_data(ttl=20, show_spinner=False)
def fetch_order_book(pair: str, exchange_id: str, depth: int = 8):
    if ccxt is None:
        raise RuntimeError("ccxt not installed")
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True, "timeout": 8000})
    ob = exchange.fetch_order_book(pair, limit=depth)
    return ob


# =============================================================================
# INDICATORS
# =============================================================================
def add_bollinger_bands(df: pd.DataFrame, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame:
    df["bb_mid"] = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + std_mult * std
    df["bb_lower"] = df["bb_mid"] - std_mult * std
    return df


def add_ema(df: pd.DataFrame, period: int, col_name: str) -> pd.DataFrame:
    df[col_name] = df["close"].ewm(span=period, adjust=False).mean()
    return df


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df["rsi"] = _rsi_series(df["close"], period)
    return df


def add_stoch_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14,
                   k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    rsi = df["rsi"] if "rsi" in df.columns else _rsi_series(df["close"], rsi_period)
    min_rsi = rsi.rolling(stoch_period).min()
    max_rsi = rsi.rolling(stoch_period).max()
    stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, np.nan)
    df["stoch_rsi_k"] = (stoch_rsi * 100).rolling(k_smooth).mean()
    df["stoch_rsi_d"] = df["stoch_rsi_k"].rolling(d_smooth).mean()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df


def add_kdj(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    low_n = df["low"].rolling(period).min()
    high_n = df["high"].rolling(period).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    k_vals, d_vals = [], []
    prev_k, prev_d = 50.0, 50.0
    for val in rsv.tolist():
        if pd.isna(val):
            k_vals.append(prev_k)
            d_vals.append(prev_d)
            continue
        cur_k = (2 / 3) * prev_k + (1 / 3) * val
        cur_d = (2 / 3) * prev_d + (1 / 3) * cur_k
        k_vals.append(cur_k)
        d_vals.append(cur_d)
        prev_k, prev_d = cur_k, cur_d

    df["kdj_k"] = k_vals
    df["kdj_d"] = d_vals
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df


def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df["vol_sma"] = df["volume"].rolling(period).mean()
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = add_bollinger_bands(df, 20, 2.0)
    df = add_ema(df, 50, "ema_50")
    df = add_ema(df, 200, "ema_200")
    df = add_rsi(df, 14)
    df = add_stoch_rsi(df)
    df = add_macd(df)
    df = add_kdj(df)
    df = add_volume_sma(df, 20)
    return df


# =============================================================================
# SIGNAL ENGINE
# =============================================================================
def generate_signal(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    score = 0.0
    reasons = []

    if last["ema_50"] > last["ema_200"]:
        score += 1
        reasons.append(("bullish", "EMA50 above EMA200 — uptrend regime"))
    else:
        score -= 1
        reasons.append(("bearish", "EMA50 below EMA200 — downtrend regime"))

    if last["close"] <= last["bb_lower"]:
        score += 1
        reasons.append(("bullish", "Price at/below lower Bollinger Band — oversold zone"))
    elif last["close"] >= last["bb_upper"]:
        score -= 1
        reasons.append(("bearish", "Price at/above upper Bollinger Band — overbought zone"))
    else:
        reasons.append(("neutral", "Price trading within Bollinger Bands"))

    if pd.notna(last["rsi"]):
        if last["rsi"] < 30:
            score += 1
            reasons.append(("bullish", f"RSI at {last['rsi']:.1f} — oversold"))
        elif last["rsi"] > 70:
            score -= 1
            reasons.append(("bearish", f"RSI at {last['rsi']:.1f} — overbought"))
        else:
            reasons.append(("neutral", f"RSI at {last['rsi']:.1f} — neutral range"))

    k, d = last["stoch_rsi_k"], last["stoch_rsi_d"]
    if pd.notna(k) and pd.notna(d):
        if k < 20 and k > d:
            score += 1
            reasons.append(("bullish", "StochRSI turning up from oversold (<20)"))
        elif k > 80 and k < d:
            score -= 1
            reasons.append(("bearish", "StochRSI turning down from overbought (>80)"))
        elif k > d:
            score += 0.5
            reasons.append(("bullish", "StochRSI %K above %D — positive momentum"))
        else:
            score -= 0.5
            reasons.append(("bearish", "StochRSI %K below %D — negative momentum"))

    if pd.notna(last["macd"]) and pd.notna(last["macd_signal"]):
        hist_rising = last["macd_hist"] > prev["macd_hist"]
        if last["macd"] > last["macd_signal"]:
            score += 1 if hist_rising else 0.5
            reasons.append(("bullish", "MACD above signal line" + (" and rising" if hist_rising else "")))
        else:
            score -= 1 if not hist_rising else 0.5
            reasons.append(("bearish", "MACD below signal line" + ("" if hist_rising else " and falling")))

    j = last["kdj_j"]
    if pd.notna(j):
        if j < 0:
            score += 1
            reasons.append(("bullish", f"KDJ J-line at {j:.1f} — deeply oversold"))
        elif j > 100:
            score -= 1
            reasons.append(("bearish", f"KDJ J-line at {j:.1f} — deeply overbought"))
        elif last["kdj_k"] > last["kdj_d"]:
            score += 0.5
            reasons.append(("bullish", "KDJ %K above %D"))
        else:
            score -= 0.5
            reasons.append(("bearish", "KDJ %K below %D"))

    if pd.notna(last["vol_sma"]) and last["vol_sma"] > 0:
        if last["volume"] > last["vol_sma"]:
            score += 0.5 if score >= 0 else -0.5
            reasons.append(("bullish" if score >= 0 else "bearish", "Volume above 20-period average"))
        else:
            reasons.append(("neutral", "Volume below 20-period average"))

    return {"score": score, "reasons": reasons}


# =============================================================================
# MAIN APP EXECUTION & RENDER WITH TOUCH ZOOM
# =============================================================================
if not st.session_state.logged_in:
    login_screen()
else:
    # Sidebar Navigation & Settings
    st.sidebar.markdown(f"**User:** `{st.session_state.username}`")
    if st.session_state.tier == "Premium Pro":
        st.sidebar.markdown("<span class='premium-badge'>PREMIUM PRO</span>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown("<span class='free-badge'>FREE TIER</span>", unsafe_allow_html=True)
    
    if st.sidebar.button("Log Out"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()

    st.sidebar.markdown("---")
    exchange = st.sidebar.selectbox("Exchange", EXCHANGES)
    
    # Restrict pairs based on tier
    available_pairs = FALLBACK_PAIRS if st.session_state.tier == "Premium Pro" else FREE_PAIRS
    pair = st.sidebar.selectbox("Pair", available_pairs)
    
    available_tfs = TIMEFRAMES if st.session_state.tier == "Premium Pro" else FREE_TIMEFRAMES
    timeframe = st.sidebar.selectbox("Timeframe", available_tfs)

    st.sidebar.markdown("### Indicator Toggles")
    show_bb = st.sidebar.checkbox("Bollinger Bands", value=True)
    show_rsi = st.sidebar.checkbox("RSI (14)", value=True)
    show_macd = st.sidebar.checkbox("MACD", value=True)
    show_kdj = st.sidebar.checkbox("KDJ", value=True)

    # Main Dashboard Header
    st.title("CryptoSignal Pro Terminal")
    
    try:
        df_raw, source_label = fetch_ohlcv(pair, timeframe, exchange)
        df = compute_indicators(df_raw)
        signal_data = generate_signal(df)

        st.caption(f"Data Source: {source_label}")

        # Metrics row
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2] if len(df) > 1 else last_row
        pct_change = ((last_row["close"] - prev_row["close"]) / prev_row["close"]) * 100

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Last Close</div><div class='metric-value'>${last_row['close']:,.2f}</div></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>24h Change</div><div class='metric-value' style='color:{'#0ecb81' if pct_change >= 0 else '#f6465d'};'>{pct_change:+.2f}%</div></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>RSI</div><div class='metric-value'>{last_row.get('rsi', 0):.1f}</div></div>", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Signal Score</div><div class='metric-value'>{signal_data['score']:+.1f}</div></div>", unsafe_allow_html=True)

        st.write("")

        # Plotly Chart with Mobile Pinch-to-Zoom Configuration
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6, 0.2, 0.2])

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="Price", increasing_line_color="#0ecb81", decreasing_line_color="#f6465d"
        ), row=1, col=1)

        if show_bb and "bb_upper" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], line=dict(color="rgba(240,185,11,0.5)", width=1), name="BB Upper"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], line=dict(color="rgba(240,185,11,0.5)", width=1), fill='tonexty', fillcolor='rgba(240,185,11,0.03)', name="BB Lower"), row=1, col=1)

        # RSI
        if show_rsi and "rsi" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], line=dict(color="#f0b90b", width=1.5), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#f6465d", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#0ecb81", row=2, col=1)

        # MACD
        if show_macd and "macd" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["macd"], line=dict(color="#2962ff", width=1.5), name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], line=dict(color="#ff6d00", width=1.5), name="Signal"), row=3, col=1)

        # Layout and Mobile Touch Configuration
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0e11",
            plot_bgcolor="#14181f",
            height=650,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False,
            dragmode='zoom',
        )

        chart_config = {
            'scrollZoom': True,
            'displayModeBar': True,
            'responsive': True,
        }

        st.plotly_chart(fig, use_container_width=True, config=chart_config)

    except Exception as e:
        st.error(f"Error loading market data: {e}")
