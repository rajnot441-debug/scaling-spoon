"""
CryptoSignal Pro — Multi-Exchange Technical Analysis Terminal
----------------------------------------------------------------
A Streamlit dashboard styled after the dark, dense, data-forward layout
common to professional crypto exchange terminals (candlesticks, a compact
order book, an indicator stack, a signal readout). This is an original UI
built in that general style — it does not reuse any specific exchange's
proprietary logo or exact pixel layout, which stays that company's IP.

Live OHLCV comes from CCXT across several exchanges, with a CoinGecko
public-API fallback if every exchange attempt fails (e.g. cloud-host
geo-blocking). Includes a simulated login flow and a Free vs Pro tier
gate unlocked by a manually-distributed activation key (see the
PRO SUBSCRIPTION section for the security caveats on that approach).

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
    "pro": {"password": "pro123", "tier": "Pro"},
}

# --- Pro subscription payment details — REPLACE THESE PLACEHOLDERS ---
PAYMENT_UPI_ID = "yourupi@bank"                       # <- put your real UPI ID here
PAYMENT_PAYPAL_LINK = "https://paypal.me/yourusername"  # <- put your real PayPal.me link here
PAYMENT_CONTACT = "you@example.com"                    # <- where users send proof of payment

# ⚠️ DEMO PLACEHOLDER ONLY. A key baked directly into app.py (or visible in
# a public repo / a deployed app's source) is NOT a real secret — anyone who
# reads the code can copy it and unlock Pro for free, and one shared key
# can't be revoked for a single leaker without breaking it for everyone else.
# This satisfies "enter a key to unlock Pro" as asked, but for real
# monetization you'd want a per-customer key generated after a verified
# payment (e.g. a Stripe/Razorpay webhook that emails a unique code) checked
# against a small backend or database — never a single constant shipped in
# client code.
PRO_ACTIVATION_KEY = "PRO_KEY_123"

# =============================================================================
# STYLE — dark, dense terminal aesthetic (original design, not a brand copy)
# =============================================================================
CUSTOM_CSS = """
<style>
    .main { background-color: #0b0e11; }
    * { font-variant-numeric: tabular-nums; }
    .metric-card {
        background: #14181f; border: 1px solid #23272f; border-radius: 10px; padding: 14px 16px;
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
    .pro-badge {
        background: linear-gradient(90deg, #f0b90b, #f8d33a); color: #1a1a1a;
        padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700;
    }
    .free-badge {
        background: #23272f; color: #848e9c; padding: 2px 9px; border-radius: 20px;
        font-size: 11px; font-weight: 700;
    }
    .lock-badge { background: #23272f; color: #5b6472; padding: 1px 7px; border-radius: 10px; font-size: 10px; }
    .ob-row { display:flex; justify-content:space-between; font-size:12.5px; padding:1px 4px; font-family: monospace; }
    .ob-ask { color:#f6465d; }
    .ob-bid { color:#0ecb81; }
    .disclaimer-box {
        background-color: #14181f; border-left: 4px solid #f6465d;
        padding: 14px 18px; border-radius: 6px; font-size: 13px; color: #b7bdc6;
    }
    .pay-box {
        background-color: #14181f; border: 1px solid #f0b90b33; border-radius: 8px;
        padding: 12px 14px; font-size: 12.5px; color: #cbd1d9;
    }
    section[data-testid="stSidebar"] { background-color: #0e1116; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE
# =============================================================================
def init_state():
    defaults = {"logged_in": False, "username": None, "tier": "Free"}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# =============================================================================
# AUTH SCREEN (SIMULATED — NOT PRODUCTION AUTH)
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
                st.caption("Demo accounts: `demo` / `demo123` (Free) or `pro` / `pro123` (Pro)")
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
    """Return a sorted list of active spot symbols quoted in USDT/USD/USDC."""
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
    """CoinGecko public-API fallback — approximate OHLC/volume, no key needed."""
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
    """
    Try the user's chosen exchange first, then the rest of the fallback
    order, then CoinGecko. Returns (df, source_label). Raises only if every
    provider fails, with all provider errors collected for display.
    """
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
    return exchange.fetch_order_book(pair, limit=depth)


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
    """All indicators are always computed (cheap) — sidebar toggles only
    control what's *displayed*; the signal engine always sees everything."""
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
# SIGNAL ENGINE — confluence across trend/BB/RSI/StochRSI/MACD/KDJ/Volume
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
            reasons.append(("neutral", "Volume above 20-period average — move is confirmed by participation"))
            score += 0.5 if score > 0 else (-0.5 if score < 0 else 0)
        else:
            reasons.append(("neutral", "Volume below average — weak conviction behind the move"))

    if score >= 2.5:
        signal = "BUY"
    elif score <= -2.5:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(100, int(abs(score) / 7 * 100))
    return {"signal": signal, "score": round(score, 2), "confidence": confidence,
            "reasons": reasons, "price": last["close"]}


# =============================================================================
# CHARTING — dynamic subplot stack driven by sidebar toggles
# =============================================================================
def build_chart(df: pd.DataFrame, pair: str, toggles: dict) -> go.Figure:
    rows = ["price"]
    if toggles.get("volume"):
        rows.append("volume")
    if toggles.get("macd"):
        rows.append("macd")
    if toggles.get("kdj"):
        rows.append("kdj")
    if toggles.get("rsi"):
        rows.append("rsi")
    if toggles.get("stochrsi"):
        rows.append("stochrsi")

    n = len(rows)
    price_h = 0.45 if n > 1 else 1.0
    remaining = 1.0 - price_h
    other_h = (remaining / (n - 1)) if n > 1 else 0
    row_heights = [price_h] + [other_h] * (n - 1)

    titles = {
        "price": f"{pair} — Price" + (" + Bollinger Bands + EMA" if (toggles.get("bb") or toggles.get("ema")) else ""),
        "volume": "Volume", "macd": "MACD (12,26,9)", "kdj": "KDJ (9)",
        "rsi": "RSI (14)", "stochrsi": "Stochastic RSI",
    }

    fig = make_subplots(
        rows=n, cols=1, shared_xaxes=True, row_heights=row_heights,
        vertical_spacing=0.035, subplot_titles=[titles[r] for r in rows],
    )
    row_of = {name: i + 1 for i, name in enumerate(rows)}

    r = row_of["price"]
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="Price", increasing_line_color="#0ecb81", decreasing_line_color="#f6465d",
    ), row=r, col=1)

    if toggles.get("bb"):
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                                  line=dict(color="rgba(100,150,255,0.5)", width=1)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                                  line=dict(color="rgba(100,150,255,0.5)", width=1),
                                  fill="tonexty", fillcolor="rgba(100,150,255,0.07)"), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_mid"], name="BB Mid (SMA20)",
                                  line=dict(color="rgba(150,150,150,0.6)", width=1, dash="dot")), row=r, col=1)

    if toggles.get("ema"):
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], name="EMA 50",
                                  line=dict(color="#f0b90b", width=1.4)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_200"], name="EMA 200",
                                  line=dict(color="#e67e22", width=1.6)), row=r, col=1)

    if "volume" in row_of:
        r = row_of["volume"]
        vol_colors = np.where(df["close"] >= df["open"], "rgba(14,203,129,0.5)", "rgba(246,70,93,0.5)")
        fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume", marker_color=vol_colors), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["vol_sma"], name="Vol SMA 20",
                                  line=dict(color="#3498db", width=1.3)), row=r, col=1)

    if "macd" in row_of:
        r = row_of["macd"]
        hist_colors = np.where(df["macd_hist"] >= 0, "rgba(14,203,129,0.6)", "rgba(246,70,93,0.6)")
        fig.add_trace(go.Bar(x=df.index, y=df["macd_hist"], name="MACD Hist", marker_color=hist_colors), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["macd"], name="MACD",
                                  line=dict(color="#3498db", width=1.4)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], name="Signal",
                                  line=dict(color="#f0b90b", width=1.4)), row=r, col=1)

    if "kdj" in row_of:
        r = row_of["kdj"]
        fig.add_trace(go.Scatter(x=df.index, y=df["kdj_k"], name="K", line=dict(color="#3498db", width=1.3)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["kdj_d"], name="D", line=dict(color="#f0b90b", width=1.3)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["kdj_j"], name="J", line=dict(color="#a55eea", width=1.3)), row=r, col=1)
        fig.add_hline(y=100, line_dash="dash", line_color="gray", row=r, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=r, col=1)

    if "rsi" in row_of:
        r = row_of["rsi"]
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI",
                                  line=dict(color="#a55eea", width=1.4)), row=r, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="gray", row=r, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="gray", row=r, col=1)

    if "stochrsi" in row_of:
        r = row_of["stochrsi"]
        fig.add_trace(go.Scatter(x=df.index, y=df["stoch_rsi_k"], name="StochRSI %K",
                                  line=dict(color="#0ecb81", width=1.4)), row=r, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["stoch_rsi_d"], name="StochRSI %D",
                                  line=dict(color="#f6465d", width=1.4)), row=r, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="gray", row=r, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="gray", row=r, col=1)

    fig.update_layout(
        height=260 * n + 120,
        template="plotly_dark",
        paper_bgcolor="#0b0e11",
        plot_bgcolor="#0b0e11",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        xaxis_rangeslider_visible=False,
        # A single finger/mouse drag no longer pans or box-zooms the chart.
        # Pinch-to-zoom is a native two-finger touch gesture handled by the
        # browser independently of dragmode, so it keeps working normally.
        dragmode=False,
    )
    for i in range(1, n + 1):
        fig.update_xaxes(row=i, col=1, showspikes=False)
    return fig


CHART_CONFIG = {
    # Mouse-wheel/trackpad scroll zoom off — this, combined with
    # dragmode=False above, is what stops a single touch from zooming.
    "scrollZoom": False,
    "displayModeBar": False,
    "doubleClick": "reset",
    "displaylogo": False,
}


# =============================================================================
# ORDER BOOK (read-only depth snapshot — no order placement)
# =============================================================================
def render_order_book(pair: str, exchange_id: str):
    try:
        ob = fetch_order_book(pair, exchange_id, depth=8)
    except Exception:
        st.caption("Order book unavailable for this exchange/pair right now.")
        return

    asks = list(reversed(ob.get("asks", [])[:8]))
    bids = ob.get("bids", [])[:8]
    if not asks and not bids:
        st.caption("Order book returned no data.")
        return

    st.markdown("**Order Book (depth 8)**")
    rows_html = []
    for price, amount in asks:
        rows_html.append(f"<div class='ob-row'><span class='ob-ask'>{price:,.2f}</span><span>{amount:.4f}</span></div>")

    if bids and asks:
        best_bid, best_ask = bids[0][0], asks[-1][0]
        spread = best_ask - best_bid
        spread_pct = (spread / best_ask * 100) if best_ask else 0
        rows_html.append(
            f"<div style='border-top:1px solid #23272f;margin:3px 0;padding:2px 4px;"
            f"font-size:11px;color:#848e9c;'>spread {spread:,.2f} ({spread_pct:.3f}%)</div>"
        )
    else:
        rows_html.append("<div style='border-top:1px solid #23272f;margin:3px 0;'></div>")

    for price, amount in bids:
        rows_html.append(f"<div class='ob-row'><span class='ob-bid'>{price:,.2f}</span><span>{amount:.4f}</span></div>")
    st.markdown("".join(rows_html), unsafe_allow_html=True)


# =============================================================================
# PRO SUBSCRIPTION — manual payment + activation key gate
# =============================================================================
def render_pro_subscription_sidebar():
    """
    NOTE ON THIS APPROACH: this is a manual, honor-system flow — the user
    pays you directly via UPI/PayPal, messages you proof of payment, and you
    manually send back the activation key. That's a legitimate way to start
    monetizing an indie tool, but be aware of its real limits:
      - There's no automatic payment verification here — you have to check
        payments yourself before handing out the key.
      - The key below is a single hardcoded string in the source, so it is
        NOT secure once this code is public (GitHub, a deployed app, etc.)
        — anyone can read it and unlock Pro without paying, and you can't
        revoke one leaked copy without changing the key for every user.
      - For real, scalable monetization, replace this block with a payment
        gateway (Stripe Checkout / Razorpay Subscriptions) that generates a
        unique per-customer key via webhook, checked against a backend/DB.
    """
    st.sidebar.divider()
    st.sidebar.header("💎 Pro Subscription")

    if st.session_state.tier == "Pro":
        st.sidebar.success("✅ Pro unlocked for this session")
        return

    with st.sidebar.expander("Unlock Pro — $2/mo or ₹150–₹200/mo", expanded=False):
        st.markdown(
            f"""
            <div class='pay-box'>
            <b>1. Pay via one of:</b><br/>
            • UPI: <code>{PAYMENT_UPI_ID}</code><br/>
            • PayPal: <a href="{PAYMENT_PAYPAL_LINK}" target="_blank">{PAYMENT_PAYPAL_LINK}</a><br/><br/>
            <b>2. Send proof of payment</b> (screenshot + your username) to
            <code>{PAYMENT_CONTACT}</code>.<br/><br/>
            <b>3. You'll receive an Activation Key</b> — enter it below to unlock Pro.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Manual, honor-system unlock for this demo — see code comments for production notes.")

        key_input = st.text_input("Activation Key / Pro Password", type="password", key="pro_key_input")
        if st.button("Activate Pro", use_container_width=True, type="primary"):
            if key_input and key_input == PRO_ACTIVATION_KEY:
                st.session_state.tier = "Pro"
                st.success("✅ Pro activated!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid activation key.")


# =============================================================================
# MAIN APP
# =============================================================================
def main_app():
    tier = st.session_state.tier
    is_pro = tier == "Pro"
    badge_class = "pro-badge" if is_pro else "free-badge"

    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(f"## 📊 CryptoSignal Pro &nbsp; <span class='{badge_class}'>{tier}</span>", unsafe_allow_html=True)
    with hcol2:
        st.markdown(f"<div style='text-align:right;padding-top:18px;'>👤 {st.session_state.username}</div>", unsafe_allow_html=True)
        if st.button("Log out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.tier = "Free"
            st.rerun()

    # ---- Sidebar: exchange, pair, timeframe ----
    st.sidebar.header("⚙️ Market Controls")

    available_exchanges = EXCHANGES if is_pro else FREE_EXCHANGES
    exchange_id = st.sidebar.selectbox("Exchange", available_exchanges)
    if not is_pro:
        st.sidebar.caption(f"🔒 {len(EXCHANGES) - len(FREE_EXCHANGES)} more exchanges on Pro")

    live_symbols = load_markets_for_exchange(exchange_id) if is_pro else []
    pair_pool = live_symbols if (is_pro and live_symbols) else (FALLBACK_PAIRS if is_pro else FREE_PAIRS)
    pair = st.sidebar.selectbox(f"Trading Pair ({len(pair_pool)} available)", pair_pool)
    if not is_pro:
        st.sidebar.caption("🔒 Full pair search unlocked on Pro")

    available_tfs = TIMEFRAMES if is_pro else FREE_TIMEFRAMES
    timeframe = st.sidebar.selectbox("Timeframe", available_tfs, index=len(available_tfs) - 2)
    if not is_pro:
        st.sidebar.caption("🔒 5m / 15m intraday timeframes are Pro only")

    st.sidebar.divider()
    st.sidebar.header("📈 Indicators")
    toggles = {
        "bb": st.sidebar.checkbox("Bollinger Bands (20,2)", value=True),
        "ema": st.sidebar.checkbox("EMA Trend (50/200)", value=True),
        "volume": st.sidebar.checkbox("Volume + SMA(20)", value=True),
        "rsi": st.sidebar.checkbox("RSI (14)", value=True),
    }
    if is_pro:
        toggles["macd"] = st.sidebar.checkbox("MACD (12,26,9)", value=True)
        toggles["kdj"] = st.sidebar.checkbox("KDJ (9)", value=False)
        toggles["stochrsi"] = st.sidebar.checkbox("Stochastic RSI", value=True)
    else:
        st.sidebar.markdown("MACD, KDJ, Stochastic RSI <span class='lock-badge'>Pro</span>", unsafe_allow_html=True)
        toggles["macd"] = toggles["kdj"] = toggles["stochrsi"] = False

    render_pro_subscription_sidebar()

    st.sidebar.divider()
    st.sidebar.caption(f"Preferred source: {exchange_id} → auto-fallback chain → CoinGecko · cached 60s")
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        fetch_ohlcv.clear()
        fetch_order_book.clear()

    # ---- Fetch + compute ----
    try:
        with st.spinner(f"Fetching live {pair} {timeframe} data..."):
            raw_df, data_source = fetch_ohlcv(pair, timeframe, exchange_id)
        df = compute_indicators(raw_df)
    except Exception as e:
        st.markdown(
            f"""
            <div class='disclaimer-box' style='border-left-color:#f6465d;'>
            ⚠️ <b>Unable to load market data right now.</b><br/>
            Every configured data provider failed for <b>{pair} / {timeframe}</b>. Details:<br/>
            <pre style='white-space:pre-wrap;font-size:11px;color:#848e9c;'>{e}</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 Retry now", use_container_width=True):
                fetch_ohlcv.clear()
                st.rerun()
        with col_b:
            st.caption("Tip: try a different exchange, pair, or timeframe.")
        st.stop()

    if "CoinGecko" in data_source:
        st.info(
            "ℹ️ Live exchange data was unavailable, so this chart is running on the **CoinGecko "
            "fallback**. Volume is an approximate rolling-average proxy, not exact per-candle volume.",
            icon="ℹ️",
        )
    elif exchange_id not in data_source:
        st.info(f"ℹ️ **{exchange_id}** was unreachable — showing data from {data_source} instead.", icon="ℹ️")

    result = generate_signal(df)

    # ---- Top metric row ----
    window = max(2, int(1440 / TF_MINUTES.get(timeframe, 60)))
    recent = df.tail(window)
    change_pct = (df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100 if len(df) > 1 else 0
    day_high, day_low, day_vol = recent["high"].max(), recent["low"].min(), recent["volume"].sum()

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, label, value, color in [
        (m1, "Last Price", f"${result['price']:,.2f}", "#eaecef"),
        (m2, f"Change ({timeframe})", f"{change_pct:+.2f}%", "#0ecb81" if change_pct >= 0 else "#f6465d"),
        (m3, "~24h High", f"${day_high:,.2f}", "#eaecef"),
        (m4, "~24h Low", f"${day_low:,.2f}", "#eaecef"),
        (m5, "~24h Volume", f"{day_vol:,.0f}", "#eaecef"),
    ]:
        with col:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>{label}</div>"
                f"<div class='metric-value' style='color:{color};'>{value}</div></div>",
                unsafe_allow_html=True,
            )

    st.write("")

    # ---- Signal + order book + chart ----
    left_col, chart_col = st.columns([1, 2.8])

    with left_col:
        css_class = {"BUY": "signal-buy", "SELL": "signal-sell", "HOLD": "signal-hold"}[result["signal"]]
        icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}[result["signal"]]
        st.markdown(f"<div class='{css_class}'>{icon} {result['signal']}</div>", unsafe_allow_html=True)
        st.write("")

        if is_pro:
            st.metric("Confidence Score", f"{result['confidence']}%")
            st.markdown("**Indicator Confluence Breakdown**")
            for kind, text in result["reasons"]:
                icon2 = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[kind]
                st.markdown(f"{icon2} {text}")
        else:
            st.info("Basic signal shown. Unlock Pro for the full breakdown, confidence score, and order book.")
            st.markdown(f"**EMA Trend:** {'Bullish' if df['ema_50'].iloc[-1] > df['ema_200'].iloc[-1] else 'Bearish'}")

        st.divider()
        if is_pro:
            render_order_book(pair, exchange_id)
        else:
            st.caption("🔒 Order book depth is a Pro feature.")

    with chart_col:
        st.plotly_chart(build_chart(df, pair, toggles), use_container_width=True, config=CHART_CONFIG)

    if is_pro:
        with st.expander("📋 Raw Indicator Data (latest 20 candles)"):
            cols = ["open", "high", "low", "close", "volume", "bb_upper", "bb_mid", "bb_lower",
                    "ema_50", "ema_200", "rsi", "stoch_rsi_k", "stoch_rsi_d",
                    "macd", "macd_signal", "kdj_k", "kdj_d", "kdj_j", "vol_sma"]
            st.dataframe(df[cols].tail(20).sort_index(ascending=False), use_container_width=True)
    else:
        st.caption("🔒 Raw indicator data export is a Pro feature.")

    st.divider()
    st.markdown(
        """
        <div class='disclaimer-box'>
        ⚠️ <b>Risk Disclaimer:</b> All signals, indicators, and content on this platform are generated
        algorithmically for <b>educational and informational purposes only</b> and do not constitute
        financial, investment, or trading advice. This platform is strictly for technical analysis —
        it never places orders, holds funds, or manages a wallet. Cryptocurrency markets are highly
        volatile; you can lose some or all of your capital. Past performance and backtested confluence
        do not guarantee future results. Authentication is simulated, and Pro access is unlocked
        manually rather than through an automated payment processor. Always do your own research and
        consult a licensed financial advisor before making investment decisions.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Data via {data_source}")


# =============================================================================
# ROUTER
# =============================================================================
if not st.session_state.logged_in:
    login_screen()
else:
    main_app()
