"""
Crypto Algorithmic Signal Platform
-----------------------------------
A Streamlit web app that fetches live OHLCV data via CCXT, computes a
technical-indicator confluence, and produces Buy/Sell/Hold signals.

Includes a simulated login/auth flow and a Free vs Premium Pro subscription
tier gate with a placeholder payment integration hook (Stripe / Razorpay).

⚠️ EDUCATIONAL USE ONLY — NOT FINANCIAL ADVICE. See disclaimer in-app.
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
    page_title="CryptoSignal Pro | Algorithmic Signal Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CONSTANTS
# =============================================================================
PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
    "LINK/USDT", "MATIC/USDT",
]
FREE_PAIRS = ["BTC/USDT", "ETH/USDT"]  # Free tier is limited

TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
FREE_TIMEFRAMES = ["1h", "4h", "1d"]  # Free tier can't access lower timeframes

EXCHANGE_ID = "binance"  # kept as the first CCXT exchange tried, see CCXT_EXCHANGES_TO_TRY

# Multiple exchanges are tried in order because some cloud hosts (e.g.
# Streamlit Community Cloud) run from IP ranges that certain exchanges
# geo-block (Binance is a common one). If every exchange fails, the app
# falls back to the CoinGecko public API further below.
CCXT_EXCHANGES_TO_TRY = ["binance", "kucoin", "bybit", "okx", "gateio", "kraken"]

# CoinGecko fallback: map our "BASE/QUOTE" pairs to CoinGecko coin IDs.
# CoinGecko's free market_chart endpoint only prices against fiat/major
# currencies (we use USD as a stand-in for USDT, which is a very close peg).
COINGECKO_ID_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "LINK": "chainlink", "MATIC": "matic-network",
}

# How many days of history to request from CoinGecko for each timeframe,
# and the pandas resample rule used to bucket the raw price/volume series
# into OHLCV candles. CoinGecko auto-selects raw granularity by day range:
# <=1 day -> ~5min data, 2-90 days -> hourly data, >90 days -> daily data.
TF_TO_CG_DAYS = {"5m": 1, "15m": 1, "1h": 30, "4h": 90, "1d": 365}
TF_TO_RESAMPLE_RULE = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}

# Demo credentials for the login simulation (NOT real auth — see disclaimer)
DEMO_USERS = {
    "demo": {"password": "demo123", "tier": "Free"},
    "pro": {"password": "pro123", "tier": "Premium Pro"},
}

CUSTOM_CSS = """
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: linear-gradient(135deg, #1a1f2b 0%, #12151d 100%);
        border: 1px solid #2a2f3a;
        border-radius: 12px;
        padding: 18px;
        text-align: center;
    }
    .signal-buy {
        background: linear-gradient(135deg, #0f5132 0%, #0a3d24 100%);
        border: 1px solid #2ecc71;
        border-radius: 14px;
        padding: 22px;
        text-align: center;
        font-size: 28px;
        font-weight: 700;
        color: #2ecc71;
    }
    .signal-sell {
        background: linear-gradient(135deg, #58151c 0%, #3d0f14 100%);
        border: 1px solid #e74c3c;
        border-radius: 14px;
        padding: 22px;
        text-align: center;
        font-size: 28px;
        font-weight: 700;
        color: #e74c3c;
    }
    .signal-hold {
        background: linear-gradient(135deg, #4d3b0a 0%, #3a2c08 100%);
        border: 1px solid #f1c40f;
        border-radius: 14px;
        padding: 22px;
        text-align: center;
        font-size: 28px;
        font-weight: 700;
        color: #f1c40f;
    }
    .premium-badge {
        background: linear-gradient(90deg, #f7971e, #ffd200);
        color: #1a1a1a;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
    }
    .free-badge {
        background: #2a2f3a;
        color: #aaa;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
    }
    .disclaimer-box {
        background-color: #1a1a1a;
        border-left: 4px solid #e74c3c;
        padding: 14px 18px;
        border-radius: 6px;
        font-size: 13px;
        color: #ccc;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE INIT
# =============================================================================
def init_state():
    defaults = {
        "logged_in": False,
        "username": None,
        "tier": "Free",
        "show_upgrade": False,
    }
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
        "<p style='text-align:center;color:#888;'>Algorithmic confluence signals for crypto markets</p>",
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
                st.caption("This is a simulated sign-up for demo purposes only.")
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
        ⚠️ <b>Risk Disclaimer:</b> This platform is for educational and informational purposes only
        and does not constitute financial advice. This login is a simulated demonstration only and
        is not a secure production authentication system. Cryptocurrency trading involves substantial
        risk of loss. Always do your own research (DYOR) and consult a licensed financial advisor
        before trading.
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# DATA FETCHING — multi-exchange CCXT with CoinGecko public-API fallback
# =============================================================================
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
    """
    Fallback data source using CoinGecko's free /market_chart endpoint
    (no API key required, generally reachable from cloud hosts that
    exchanges like Binance geo-block).

    Note: CoinGecko's public endpoint returns a price time series and a
    rolling total-volume series rather than true per-candle OHLCV, so we
    reconstruct approximate OHLC via resample().ohlc() on price, and use
    the mean of the rolling volume series per bucket as an approximate
    volume proxy. This is clearly labeled in the UI as approximate.
    """
    base = pair.split("/")[0].upper()
    coin_id = COINGECKO_ID_MAP.get(base)
    if not coin_id:
        raise ValueError(f"No CoinGecko mapping for base asset '{base}'")

    days = TF_TO_CG_DAYS.get(timeframe, 30)
    rule = TF_TO_RESAMPLE_RULE.get(timeframe, "1h")

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    resp = requests.get(
        url, params={"vs_currency": "usd", "days": days}, timeout=10
    )
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
def fetch_ohlcv(pair: str, timeframe: str, limit: int = 300):
    """
    Returns (df, source_label). Tries several CCXT exchanges in order (to
    route around per-exchange geo-blocking on cloud hosts), then falls back
    to the CoinGecko public API if every exchange attempt fails. Raises only
    if every provider fails, with all provider errors collected for display.
    """
    errors = []

    if ccxt is not None:
        for exchange_id in CCXT_EXCHANGES_TO_TRY:
            try:
                df = _fetch_ohlcv_ccxt(pair, timeframe, limit, exchange_id)
                return df, f"{exchange_id} (via CCXT)"
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

    raise RuntimeError(
        "All data providers failed:\n- " + "\n- ".join(errors)
    )


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


def add_stoch_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14,
                   k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    min_rsi = rsi.rolling(stoch_period).min()
    max_rsi = rsi.rolling(stoch_period).max()
    stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, np.nan)

    df["rsi"] = rsi
    df["stoch_rsi_k"] = (stoch_rsi * 100).rolling(k_smooth).mean()
    df["stoch_rsi_d"] = df["stoch_rsi_k"].rolling(d_smooth).mean()
    return df


def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df["vol_sma"] = df["volume"].rolling(period).mean()
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = add_bollinger_bands(df, 20, 2.0)
    df = add_ema(df, 50, "ema_50")
    df = add_ema(df, 200, "ema_200")
    df = add_stoch_rsi(df)
    df = add_volume_sma(df, 20)
    return df


# =============================================================================
# SIGNAL ENGINE — confluence of BB, EMA trend, StochRSI, Volume
# =============================================================================
def generate_signal(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    score = 0
    reasons = []

    # 1) Trend via EMA 50/200 (golden/death cross regime)
    if last["ema_50"] > last["ema_200"]:
        score += 1
        reasons.append(("bullish", "EMA50 above EMA200 — uptrend regime"))
    else:
        score -= 1
        reasons.append(("bearish", "EMA50 below EMA200 — downtrend regime"))

    # 2) Price position vs Bollinger Bands (mean reversion / breakout)
    if last["close"] <= last["bb_lower"]:
        score += 1
        reasons.append(("bullish", "Price at/below lower Bollinger Band — oversold zone"))
    elif last["close"] >= last["bb_upper"]:
        score -= 1
        reasons.append(("bearish", "Price at/above upper Bollinger Band — overbought zone"))
    else:
        reasons.append(("neutral", "Price trading within Bollinger Bands"))

    # 3) Stochastic RSI momentum
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

    # 4) Volume confirmation
    if last["volume"] > last["vol_sma"]:
        reasons.append(("neutral", "Volume above 20-period average — move is confirmed by participation"))
        score += 0.5 if score > 0 else (-0.5 if score < 0 else 0)
    else:
        reasons.append(("neutral", "Volume below average — weak conviction behind the move"))

    if score >= 1.5:
        signal = "BUY"
    elif score <= -1.5:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(100, int(abs(score) / 4 * 100))

    return {
        "signal": signal,
        "score": round(score, 2),
        "confidence": confidence,
        "reasons": reasons,
        "price": last["close"],
    }


# =============================================================================
# CHARTING
# =============================================================================
def build_chart(df: pd.DataFrame, pair: str) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.2, 0.25],
        vertical_spacing=0.03,
        subplot_titles=(f"{pair} — Price, Bollinger Bands & EMA", "Volume", "Stochastic RSI"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="Price", increasing_line_color="#2ecc71", decreasing_line_color="#e74c3c",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                              line=dict(color="rgba(100,150,255,0.5)", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                              line=dict(color="rgba(100,150,255,0.5)", width=1),
                              fill="tonexty", fillcolor="rgba(100,150,255,0.07)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_mid"], name="BB Mid (SMA20)",
                              line=dict(color="rgba(150,150,150,0.6)", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], name="EMA 50",
                              line=dict(color="#f1c40f", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["ema_200"], name="EMA 200",
                              line=dict(color="#e67e22", width=1.6)), row=1, col=1)

    # Plotly's color validator doesn't accept 8-digit hex (#RRGGBBAA) — use
    # rgba() instead, which is the format it actually supports for alpha.
    vol_colors = np.where(
        df["close"] >= df["open"],
        "rgba(46,204,113,0.4)",   # green, translucent
        "rgba(231,76,60,0.4)",    # red, translucent
    )
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume", marker_color=vol_colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["vol_sma"], name="Vol SMA 20",
                              line=dict(color="#3498db", width=1.3)), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["stoch_rsi_k"], name="StochRSI %K",
                              line=dict(color="#2ecc71", width=1.4)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["stoch_rsi_d"], name="StochRSI %D",
                              line=dict(color="#e74c3c", width=1.4)), row=3, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="gray", row=3, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="gray", row=3, col=1)

    fig.update_layout(
        height=780,
        template="plotly_dark",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        xaxis_rangeslider_visible=False,
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="StochRSI", row=3, col=1, range=[0, 100])
    return fig


# =============================================================================
# SUBSCRIPTION / PAYMENT PLACEHOLDER
# =============================================================================
def render_upgrade_modal():
    st.markdown("### 🔓 Upgrade to Premium Pro")
    st.write(
        "Unlock all 10 pairs, intraday timeframes (5m/15m), full indicator "
        "breakdowns, and confidence-scored signals."
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Free**")
        st.markdown("- 2 pairs (BTC, ETH)\n- 1h / 4h / 1d timeframes\n- Basic Buy/Sell/Hold signal")
    with col2:
        st.markdown("**Premium Pro — $19/mo**")
        st.markdown("- All 10 pairs\n- All timeframes incl. 5m/15m\n- Full indicator confluence breakdown\n- Confidence score")

    st.write("")
    pay_provider = st.radio("Choose payment provider", ["Stripe", "Razorpay"], horizontal=True)
    if st.button(f"Pay with {pay_provider} (Demo)", type="primary"):
        # --- PAYMENT INTEGRATION PLACEHOLDER ---
        # Replace this block with a real server-side call, e.g.:
        #
        # Stripe:
        #   import stripe
        #   stripe.api_key = st.secrets["STRIPE_SECRET_KEY"]
        #   session = stripe.checkout.Session.create(
        #       payment_method_types=["card"],
        #       line_items=[{"price": "price_xxx", "quantity": 1}],
        #       mode="subscription",
        #       success_url="https://yourapp.com/success",
        #       cancel_url="https://yourapp.com/cancel",
        #   )
        #   st.link_button("Complete Payment", session.url)
        #
        # Razorpay:
        #   import razorpay
        #   client = razorpay.Client(auth=(key_id, key_secret))
        #   subscription = client.subscription.create({...})
        #
        # NEVER put live secret keys in client-side code. Use st.secrets
        # and a backend/webhook to verify payment before granting access.
        with st.spinner("Redirecting to payment provider (simulated)..."):
            time.sleep(1.2)
        st.session_state.tier = "Premium Pro"
        st.success("Payment simulated successfully — you're now on Premium Pro!")
        time.sleep(0.8)
        st.session_state.show_upgrade = False
        st.rerun()


# =============================================================================
# MAIN APP
# =============================================================================
def main_app():
    tier = st.session_state.tier
    badge_class = "premium-badge" if tier == "Premium Pro" else "free-badge"

    # ---- Header ----
    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(
            f"## 📊 CryptoSignal Pro &nbsp; <span class='{badge_class}'>{tier}</span>",
            unsafe_allow_html=True,
        )
    with hcol2:
        st.markdown(f"<div style='text-align:right;padding-top:18px;'>👤 {st.session_state.username}</div>", unsafe_allow_html=True)
        if st.button("Log out", use_container_width=True):
            for k in ["logged_in", "username", "tier", "show_upgrade"]:
                st.session_state[k] = False if k in ("logged_in", "show_upgrade") else None
            st.session_state.tier = "Free"
            st.rerun()

    # ---- Sidebar controls ----
    st.sidebar.header("⚙️ Signal Controls")

    available_pairs = PAIRS if tier == "Premium Pro" else FREE_PAIRS
    pair = st.sidebar.selectbox("Trading Pair", available_pairs)
    if tier != "Premium Pro":
        st.sidebar.caption(f"🔒 {len(PAIRS) - len(FREE_PAIRS)} more pairs available on Premium Pro")

    available_tfs = TIMEFRAMES if tier == "Premium Pro" else FREE_TIMEFRAMES
    timeframe = st.sidebar.selectbox("Timeframe", available_tfs, index=len(available_tfs) - 2)
    if tier != "Premium Pro":
        st.sidebar.caption("🔒 5m / 15m intraday timeframes are Premium Pro only")

    st.sidebar.divider()
    if tier != "Premium Pro":
        if st.sidebar.button("⭐ Upgrade to Premium Pro", use_container_width=True, type="primary"):
            st.session_state.show_upgrade = True
    else:
        st.sidebar.success("✅ Premium Pro active")

    st.sidebar.divider()
    st.sidebar.caption(
        "Data source: tries " + ", ".join(CCXT_EXCHANGES_TO_TRY) +
        " (via CCXT), then falls back to CoinGecko · cached 60s"
    )
    refresh = st.sidebar.button("🔄 Refresh Data", use_container_width=True)
    if refresh:
        fetch_ohlcv.clear()

    if st.session_state.show_upgrade:
        with st.container(border=True):
            render_upgrade_modal()
        st.divider()

    # ---- Fetch + compute (multi-exchange CCXT, falls back to CoinGecko) ----
    try:
        with st.spinner(f"Fetching live {pair} {timeframe} data..."):
            raw_df, data_source = fetch_ohlcv(pair, timeframe)
        df = compute_indicators(raw_df)
    except Exception as e:
        st.markdown(
            f"""
            <div class='disclaimer-box' style='border-left-color:#e74c3c;'>
            ⚠️ <b>Unable to load market data right now.</b><br/>
            Every configured data provider failed for <b>{pair} / {timeframe}</b>
            (exchanges are commonly geo-blocked on cloud hosts, and public APIs
            occasionally rate-limit). Details:<br/>
            <pre style='white-space:pre-wrap;font-size:11px;color:#999;'>{e}</pre>
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
            st.caption("Tip: try a different pair/timeframe, or wait a minute for rate limits to reset.")
        st.stop()

    if "CoinGecko" in data_source:
        st.info(
            "ℹ️ Live exchange data was unavailable (likely geo-blocked on this host), so this "
            "chart is running on the **CoinGecko fallback**. OHLC is reconstructed from CoinGecko's "
            "price series and volume is an approximate rolling-average proxy, not exact per-candle "
            "volume — treat volume-based readings with extra caution.",
            icon="ℹ️",
        )

    result = generate_signal(df)

    # ---- Top metric row ----
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"<div class='metric-card'><div style='color:#888;font-size:13px;'>Last Price</div>"
            f"<div style='font-size:24px;font-weight:700;'>${result['price']:,.2f}</div></div>",
            unsafe_allow_html=True,
        )
    with m2:
        change = (df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100 if len(df) > 1 else 0
        color = "#2ecc71" if change >= 0 else "#e74c3c"
        st.markdown(
            f"<div class='metric-card'><div style='color:#888;font-size:13px;'>Change ({timeframe})</div>"
            f"<div style='font-size:24px;font-weight:700;color:{color};'>{change:+.2f}%</div></div>",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"<div class='metric-card'><div style='color:#888;font-size:13px;'>StochRSI %K</div>"
            f"<div style='font-size:24px;font-weight:700;'>{df['stoch_rsi_k'].iloc[-1]:.1f}</div></div>",
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"<div class='metric-card'><div style='color:#888;font-size:13px;'>Volume vs Avg</div>"
            f"<div style='font-size:24px;font-weight:700;'>{(df['volume'].iloc[-1] / df['vol_sma'].iloc[-1] * 100 if df['vol_sma'].iloc[-1] else 0):.0f}%</div></div>",
            unsafe_allow_html=True,
        )

    st.write("")

    # ---- Signal + chart layout ----
    sig_col, chart_col = st.columns([1, 2.6])

    with sig_col:
        css_class = {"BUY": "signal-buy", "SELL": "signal-sell", "HOLD": "signal-hold"}[result["signal"]]
        icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}[result["signal"]]
        st.markdown(f"<div class='{css_class}'>{icon} {result['signal']}</div>", unsafe_allow_html=True)
        st.write("")

        if tier == "Premium Pro":
            st.metric("Confidence Score", f"{result['confidence']}%")
            st.markdown("**Indicator Confluence Breakdown**")
            for kind, text in result["reasons"]:
                icon2 = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[kind]
                st.markdown(f"{icon2} {text}")
        else:
            st.info("Basic signal shown. Upgrade to Premium Pro for the full indicator breakdown and confidence score.")
            st.markdown(f"**EMA Trend:** {'Bullish' if df['ema_50'].iloc[-1] > df['ema_200'].iloc[-1] else 'Bearish'}")

    with chart_col:
        st.plotly_chart(build_chart(df, pair), use_container_width=True)

    # ---- Data table (Premium only) ----
    if tier == "Premium Pro":
        with st.expander("📋 Raw Indicator Data (latest 20 candles)"):
            cols = ["open", "high", "low", "close", "volume", "bb_upper", "bb_mid",
                    "bb_lower", "ema_50", "ema_200", "stoch_rsi_k", "stoch_rsi_d", "vol_sma"]
            st.dataframe(df[cols].tail(20).sort_index(ascending=False), use_container_width=True)
    else:
        st.caption("🔒 Raw indicator data export is a Premium Pro feature.")

    # ---- Disclaimer ----
    st.divider()
    st.markdown(
        """
        <div class='disclaimer-box'>
        ⚠️ <b>Risk Disclaimer:</b> All signals, indicators, and content on this platform are generated
        algorithmically for <b>educational and informational purposes only</b> and do not constitute
        financial, investment, or trading advice. Cryptocurrency markets are highly volatile — you can
        lose some or all of your capital. Past performance and backtested confluence do not guarantee
        future results. This is a demo application: authentication is simulated and no real payments are
        processed. Always do your own research and consult a licensed financial advisor before making
        investment decisions.
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
