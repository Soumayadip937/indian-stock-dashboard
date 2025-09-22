import os
import logging
from datetime import datetime, timedelta
from time import time

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import requests
from config import Config

# Logging
logging.basicConfig(level=logging.INFO)

# Proxy base (set in Render as env var YAHOO_PROXY_URL)
YAHOO_PROXY_URL = os.environ.get("YAHOO_PROXY_URL", "").rstrip("/")

# Paths to frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

# Serve frontend from Flask to avoid CORS
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# HTTP session
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

# Health
@app.route("/api/health")
def health():
    return {"ok": True}

# ---------- Helpers ----------
def normalize_symbol(sym: str) -> str:
    fixes = {"RELIENCE": "RELIANCE"}
    return fixes.get(sym, sym)

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['SMA_20'] = df['Close'].rolling(window=20, min_periods=1).mean()
    df['SMA_50'] = df['Close'].rolling(window=50, min_periods=1).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain.replace(0, np.nan) / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    df['BB_middle'] = df['Close'].rolling(window=20, min_periods=1).mean()
    bb_std = df['Close'].rolling(window=20, min_periods=1).std()
    df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
    df['BB_lower'] = df['BB_middle'] - (bb_std * 2)
    return df

def get_stock_recommendation(stock_data: pd.DataFrame, user_profile):
    latest = stock_data.iloc[-1]
    score = 0
    reasons = []
    if latest['Close'] > latest['SMA_20']:
        score += 20; reasons.append("Price above 20-day moving average (Bullish)")
    if latest['Close'] > latest['SMA_50']:
        score += 15; reasons.append("Price above 50-day moving average (Strong trend)")
    if pd.notna(latest.get('RSI')):
        if 30 < latest['RSI'] < 70:
            score += 20; reasons.append(f"RSI at {latest['RSI']:.2f} - Normal range")
        elif latest['RSI'] <= 30:
            score += 25; reasons.append(f"RSI at {latest['RSI']:.2f} - Oversold (Potential buy)")
    if pd.notna(latest.get('BB_lower')) and latest['Close'] < latest['BB_lower']:
        score += 20; reasons.append("Price below lower Bollinger Band (Oversold)")
    if 'Volume' in stock_data.columns:
        avg_volume = stock_data['Volume'].rolling(window=20, min_periods=1).mean().iloc[-1]
        try:
            if pd.notna(latest['Volume']) and pd.notna(avg_volume) and latest['Volume'] > avg_volume * 1.5:
                score += 15; reasons.append("High volume activity")
        except Exception:
            pass
    volatility = stock_data['Close'].pct_change().std() * np.sqrt(252) * 100
    risk_level = "Low" if volatility < 20 else "Medium" if volatility < 40 else "High"
    risk_match = True
    if (user_profile or {}).get('risk_tolerance') == 'low' and risk_level == 'High':
        risk_match = False; score -= 30
    return {
        'score': int(score),
        'rating': 'Strong Buy' if score >= 70 else 'Buy' if score >= 50 else 'Hold' if score >= 30 else 'Sell',
        'reasons': reasons,
        'risk_level': risk_level,
        'volatility': float(volatility) if pd.notna(volatility) else 0.0,
        'risk_match': risk_match
    }

def safe_float(x, default=0.0):
    try:
        f = float(x)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except Exception:
        return default

# Simple in-memory cache
CACHE = {}
CACHE_TTL = 120  # seconds

def cache_get(key):
    item = CACHE.get(key)
    if not item: return None
    if time() - item['ts'] > CACHE_TTL:
        CACHE.pop(key, None); return None
    return item['val']

def cache_set(key, val):
    CACHE[key] = {'ts': time(), 'val': val}

def yahoo_proxy_fetch_series(symbol: str, exchange: str):
    """Fetch OHLC via Cloudflare Worker proxy to Yahoo chart API."""
    if not YAHOO_PROXY_URL:
        return None
    suffix = "NS" if exchange == "NSE" else "BO"
    ticker = f"{symbol}.{suffix}"
    ck = f"yh:{ticker}"
    c = cache_get(ck)
    if c is not None:
        return c
    url = f"{YAHOO_PROXY_URL}/chart/{ticker}?range=6mo&interval=1d&includePrePost=false&events=div%2Csplits"
    try:
        r = session.get(url, timeout=12)
        if r.status_code != 200:
            app.logger.warning("Worker status %s for %s", r.status_code, ticker)
            return None
        j = r.json()
    except Exception as e:
        app.logger.warning("Worker fetch failed %s: %s", ticker, e)
        return None

    chart = j.get('chart', {})
    if chart.get('error'):
        return None
    results = chart.get('result')
    if not results:
        return None
    r0 = results[0]
    ts = r0.get('timestamp', []) or []
    ind = r0.get('indicators', {}).get('quote', [{}])[0]
    if not ts or 'close' not in ind:
        return None

    df = pd.DataFrame({
        "Date": pd.to_datetime(ts, unit='s'),
        "Open": pd.to_numeric(ind.get('open', []), errors='coerce'),
        "High": pd.to_numeric(ind.get('high', []), errors='coerce'),
        "Low": pd.to_numeric(ind.get('low', []), errors='coerce'),
        "Close": pd.to_numeric(ind.get('close', []), errors='coerce'),
        "Volume": pd.to_numeric(ind.get('volume', []), errors='coerce')
    }).dropna(how='all').sort_values("Date").reset_index(drop=True)

    cache_set(ck, df)
    return df

def fetch_series_india(sym: str):
    """Try NSE then BSE via Yahoo proxy only."""
    df = yahoo_proxy_fetch_series(sym, "NSE")
    if df is not None and not df.empty:
        return df, "NSE"
    df = yahoo_proxy_fetch_series(sym, "BSE")
    if df is not None and not df.empty:
        return df, "BSE"
    return None, None

# ---------- API ----------
@app.route('/api/search/<symbol>')
def api_search(symbol):
    try:
        if not YAHOO_PROXY_URL:
            return jsonify({'error': 'Server not configured: set YAHOO_PROXY_URL'}), 503

        sym = normalize_symbol((symbol or "").upper().strip())
        hist, exchange_used = fetch_series_india(sym)
        if hist is None or hist.empty:
            return jsonify({'error': 'Stock not found or no data available'}), 404

        hist = calculate_technical_indicators(hist)

        last_close = safe_float(hist['Close'].iloc[-1], 0.0)
        prev_close = safe_float(hist['Close'].iloc[-2], last_close) if len(hist) > 1 else last_close
        current_price = last_close
        change = current_price - prev_close
        change_percent = (change / prev_close * 100.0) if prev_close else 0.0

        vol = int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns and pd.notna(hist['Volume'].iloc[-1]) else 0
        week_52_high = safe_float(hist['High'].tail(252).max() if len(hist) >= 2 else hist['High'].max(), last_close)
        week_52_low = safe_float(hist['Low'].tail(252).min() if len(hist) >= 2 else hist['Low'].min(), last_close)

        hist_tail = hist.tail(60).copy()
        hist_tail['Date'] = pd.to_datetime(hist_tail['Date']).dt.strftime('%Y-%m-%d')

        return jsonify({
            'symbol': sym,
            'exchange': exchange_used or '-',
            'name': sym,
            'current_price': current_price,
            'previous_close': prev_close,
            'change': change,
            'change_percent': change_percent,
            'volume': vol,
            'market_cap': 0,
            'pe_ratio': 0,
            'week_52_high': week_52_high,
            'week_52_low': week_52_low,
            'historical_data': hist_tail[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict('records')
        })

    except Exception as e:
        app.logger.exception("api_search failed for %s", symbol)
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500

@app.route('/api/recommendations', methods=['POST'])
def api_recommendations():
    """Keep list small to avoid rate/CPU limits."""
    try:
        if not YAHOO_PROXY_URL:
            return jsonify([])

        user_profile = request.json or {}
        budget = user_profile.get('budget', 100000)

        stocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN']  # small to be safe
        recs = []
        for sym in stocks:
            sym = normalize_symbol(sym)
            hist, _ex = fetch_series_india(sym)
            if hist is None or hist.empty:
                continue
            hist = calculate_technical_indicators(hist)
            price = safe_float(hist['Close'].iloc[-1], 0.0)
            if price <= 0 or price > budget:
                continue
            recommendation = get_stock_recommendation(hist, user_profile)
            if recommendation['score'] >= 40:
                recs.append({
                    'symbol': sym,
                    'name': sym,
                    'current_price': price,
                    'recommendation': recommendation,
                    'shares_affordable': int(budget / price) if price > 0 else 0
                })
        recs.sort(key=lambda x: x['recommendation']['score'], reverse=True)
        return jsonify(recs[:10])
    except Exception as e:
        app.logger.exception("api_recommendations failed")
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500

@app.route('/api/news/<symbol>')
def api_news(symbol):
    try:
        news = [
            {'title': f'Latest updates on {symbol}', 'source': 'Economic Times', 'url': '#', 'published': datetime.now().isoformat()},
            {'title': f'{symbol} quarterly results announced', 'source': 'Business Standard', 'url': '#', 'published': (datetime.now() - timedelta(days=1)).isoformat()},
        ]
        return jsonify(news)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Debug endpoint (optional)
@app.route('/api/debug/chart/<symbol>')
def debug_chart(symbol):
    if not YAHOO_PROXY_URL:
        return jsonify({'error': 'YAHOO_PROXY_URL not set'}), 503
    sym = normalize_symbol((symbol or "").upper().strip())
    url = f"{YAHOO_PROXY_URL}/chart/{sym}.NS?range=6mo&interval=1d"
    try:
        r = session.get(url, timeout=10)
        snippet = r.text[:200].replace("\n", " ")
        return jsonify({"status": r.status_code, "content_type": r.headers.get("content-type", ""), "snippet": snippet})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
