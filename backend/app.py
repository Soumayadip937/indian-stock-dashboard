import os
import logging
from datetime import datetime, timedelta
from time import time

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import requests
# yfinance is kept installed only as a fallback if you remove Twelve Data later
# import yfinance as yf
from config import Config

# Logging
logging.basicConfig(level=logging.INFO)

# Twelve Data key (free). Set in Render env: TWELVEDATA_API_KEY
TD_KEY = os.environ.get("TWELVEDATA_API_KEY")
TD_BASE = "https://api.twelvedata.com"

# Paths to frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

# Serve frontend from Flask to avoid CORS
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Shared session
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
})

# ---------- Frontend routes ----------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(os.path.join(app.static_folder, "css"), filename)

@app.route("/js/<path:filename>")
def js(filename):
    return send_from_directory(os.path.join(app.static_folder, "js"), filename)

@app.route("/favicon.ico")
def favicon():
    path = os.path.join(app.static_folder, "favicon.ico")
    if os.path.exists(path):
        return send_from_directory(app.static_folder, "favicon.ico")
    return ("", 204)

# Optional health check
@app.route("/api/health")
def health():
    return {"ok": True}

# ---------- Helpers ----------
def normalize_symbol(sym: str) -> str:
    # Fix common typos (RELIENCE -> RELIANCE)
    fixes = {"RELIENCE": "RELIANCE"}
    return fixes.get(sym, sym)

def get_indian_stock_ticker(symbol, exchange='NSE'):
    """Yahoo suffixes (kept for reference/fallback), not used with Twelve Data"""
    if exchange == 'NSE':
        return f"{symbol}{Config.NSE_SUFFIX}"
    elif exchange == 'BSE':
        return f"{symbol}{Config.BSE_SUFFIX}"
    return symbol

def td_symbol(symbol: str, exchange: str) -> str:
    # Twelve Data uses "SYMBOL:NSE" / "SYMBOL:BSE"
    return f"{symbol}:{exchange}"

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate basic technical indicators"""
    df = df.copy()
    # Simple Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20, min_periods=1).mean()
    df['SMA_50'] = df['Close'].rolling(window=50, min_periods=1).mean()

    # RSI (simple)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain.replace(0, np.nan) / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['BB_middle'] = df['Close'].rolling(window=20, min_periods=1).mean()
    bb_std = df['Close'].rolling(window=20, min_periods=1).std()
    df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
    df['BB_lower'] = df['BB_middle'] - (bb_std * 2)

    return df

def get_stock_recommendation(stock_data: pd.DataFrame, user_profile):
    """Generate stock recommendations based on technical analysis and user profile"""
    latest = stock_data.iloc[-1]

    score = 0
    reasons = []

    # Price vs Moving Averages
    if latest['Close'] > latest['SMA_20']:
        score += 20
        reasons.append("Price above 20-day moving average (Bullish)")

    if latest['Close'] > latest['SMA_50']:
        score += 15
        reasons.append("Price above 50-day moving average (Strong trend)")

    # RSI Analysis
    if pd.notna(latest.get('RSI')):
        if 30 < latest['RSI'] < 70:
            score += 20
            reasons.append(f"RSI at {latest['RSI']:.2f} - Normal range")
        elif latest['RSI'] <= 30:
            score += 25
            reasons.append(f"RSI at {latest['RSI']:.2f} - Oversold (Potential buy)")

    # Bollinger Bands
    if pd.notna(latest.get('BB_lower')) and latest['Close'] < latest['BB_lower']:
        score += 20
        reasons.append("Price below lower Bollinger Band (Oversold)")

    # Volume analysis (best-effort)
    if 'Volume' in stock_data.columns:
        avg_volume = stock_data['Volume'].rolling(window=20, min_periods=1).mean().iloc[-1]
        try:
            if pd.notna(latest['Volume']) and pd.notna(avg_volume) and latest['Volume'] > avg_volume * 1.5:
                score += 15
                reasons.append("High volume activity")
        except Exception:
            pass

    # Risk assessment
    volatility = stock_data['Close'].pct_change().std() * np.sqrt(252) * 100
    risk_level = "Low" if volatility < 20 else "Medium" if volatility < 40 else "High"

    # Match with user profile
    risk_match = True
    if (user_profile or {}).get('risk_tolerance') == 'low' and risk_level == 'High':
        risk_match = False
        score -= 30

    recommendation = {
        'score': int(score),
        'rating': 'Strong Buy' if score >= 70 else 'Buy' if score >= 50 else 'Hold' if score >= 30 else 'Sell',
        'reasons': reasons,
        'risk_level': risk_level,
        'volatility': float(volatility) if pd.notna(volatility) else 0.0,
        'risk_match': risk_match
    }

    return recommendation

def safe_float(x, default=0.0):
    try:
        f = float(x)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except Exception:
        return default

# Simple in-memory cache to reduce API hits (TTL seconds)
CACHE = {}
CACHE_TTL = 90  # seconds

def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    if time() - item['ts'] > CACHE_TTL:
        CACHE.pop(key, None)
        return None
    return item['val']

def cache_set(key, val):
    CACHE[key] = {'ts': time(), 'val': val}

def td_fetch_series(symbol: str, exchange: str):
    """Fetch up to 365 days of daily candles from Twelve Data for SYMBOL:EXCHANGE."""
    if not TD_KEY:
        return None  # key not set; caller will handle
    symbol_ex = td_symbol(symbol, exchange)
    cache_key = f"td:{symbol_ex}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "symbol": symbol_ex,
        "interval": "1day",
        "outputsize": "365",
        "apikey": TD_KEY,
        "timezone": "Asia/Kolkata",
        "order": "ASC"  # oldest -> newest
    }
    try:
        r = session.get(f"{TD_BASE}/time_series", params=params, timeout=12)
        j = r.json()
    except Exception as e:
        app.logger.warning("TwelveData request failed for %s: %s", symbol_ex, e)
        return None

    if not isinstance(j, dict) or j.get("status") != "ok" or "values" not in j:
        # Example error: {'code': 429, 'message': 'API rate limit exceeded'}
        app.logger.warning("TwelveData error for %s: %s", symbol_ex, j)
        return None

    vals = j["values"]
    if not vals:
        return None

    df = pd.DataFrame(vals)
    # Expected columns: datetime, open, high, low, close, volume
    # Ensure numeric types and ascending order
    df["Date"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
    })
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].sort_values("Date").reset_index(drop=True)

    cache_set(cache_key, df)
    return df

# ---------- API ----------
@app.route('/api/search/<symbol>')
def search_stock(symbol):
    """Search for stock information via Twelve Data (free key required)."""
    try:
        sym = normalize_symbol((symbol or "").upper().strip())

        # Try NSE then BSE via Twelve Data
        exchange_used = "NSE"
        hist = td_fetch_series(sym, "NSE")
        if hist is None or hist.empty:
            exchange_used = "BSE"
            hist = td_fetch_series(sym, "BSE")

        if hist is None or hist.empty:
            return jsonify({'error': 'Stock not found or no data available'}), 404

        # Indicators
        hist = calculate_technical_indicators(hist)

        # Prices
        last_close = safe_float(hist['Close'].iloc[-1], 0.0)
        prev_close = safe_float(hist['Close'].iloc[-2], last_close) if len(hist) > 1 else last_close
        current_price = last_close  # EOD data from TD
        previous_close = prev_close
        change = current_price - previous_close
        change_percent = (change / previous_close * 100.0) if previous_close else 0.0

        # Volume, 52-week highs/lows from available history (approx)
        vol = int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns and pd.notna(hist['Volume'].iloc[-1]) else 0
        week_52_high = safe_float(hist['High'].tail(252).max() if len(hist) >= 2 else hist['High'].max(), last_close)
        week_52_low = safe_float(hist['Low'].tail(252).min() if len(hist) >= 2 else hist['Low'].min(), last_close)

        # Prepare last 60 rows with Date string
        hist_tail = hist.tail(60).copy()
        hist_tail['Date'] = pd.to_datetime(hist_tail['Date']).dt.strftime('%Y-%m-%d')

        response = {
            'symbol': sym,
            'exchange': exchange_used,
            'name': sym,
            'current_price': current_price,
            'previous_close': previous_close,
            'change': change,
            'change_percent': change_percent,
            'volume': vol,
            'market_cap': 0,  # not available on free TD time_series
            'pe_ratio': 0,    # not available on free TD time_series
            'week_52_high': week_52_high,
            'week_52_low': week_52_low,
            'historical_data': hist_tail[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict('records')
        }

        return jsonify(response)

    except Exception as e:
        app.logger.exception("search_stock failed for %s", symbol)
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """Get stock recommendations based on user profile using Twelve Data history."""
    try:
        user_profile = request.json or {}
        budget = user_profile.get('budget', 100000)

        stocks_to_analyze = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR',
            'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'LT',
            'HCLTECH', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'TITAN'
        ]

        recommendations = []

        for sym in stocks_to_analyze:
            try:
                sym = normalize_symbol(sym)
                hist = td_fetch_series(sym, "NSE")
                if hist is None or hist.empty:
                    hist = td_fetch_series(sym, "BSE")
                    if hist is None or hist.empty:
                        continue

                hist = calculate_technical_indicators(hist)
                current_price = safe_float(hist['Close'].iloc[-1], 0.0)

                if current_price <= 0 or current_price > budget:
                    continue

                recommendation = get_stock_recommendation(hist, user_profile)

                if recommendation['score'] >= 40:
                    recommendations.append({
                        'symbol': sym,
                        'name': sym,
                        'current_price': current_price,
                        'recommendation': recommendation,
                        'shares_affordable': int(budget / current_price) if current_price > 0 else 0
                    })
            except Exception as inner_e:
                app.logger.warning("Screening %s failed: %s", sym, inner_e)
                continue

        recommendations.sort(key=lambda x: x['recommendation']['score'], reverse=True)
        return jsonify(recommendations[:10])

    except Exception as e:
        app.logger.exception("recommendations failed")
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500

@app.route('/api/news/<symbol>')
def get_news(symbol):
    """Get latest news for a stock (mock data for now)"""
    try:
        news = [
            {
                'title': f'Latest updates on {symbol}',
                'source': 'Economic Times',
                'url': '#',
                'published': datetime.now().isoformat()
            },
            {
                'title': f'{symbol} quarterly results announced',
                'source': 'Business Standard',
                'url': '#',
                'published': (datetime.now() - timedelta(days=1)).isoformat()
            }
        ]
        return jsonify(news)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
