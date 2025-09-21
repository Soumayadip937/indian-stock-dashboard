import os
import logging
from datetime import datetime, timedelta
from json import JSONDecodeError

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from config import Config

# Logging
logging.basicConfig(level=logging.INFO)

# Paths to frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

# Serve frontend from Flask to avoid CORS
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Persistent session with a real UA to reduce 403/empty responses from Yahoo
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache"
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
def get_indian_stock_ticker(symbol, exchange='NSE'):
    """Convert symbol to Yahoo Finance format for Indian stocks"""
    if exchange == 'NSE':
        return f"{symbol}{Config.NSE_SUFFIX}"
    elif exchange == 'BSE':
        return f"{symbol}{Config.BSE_SUFFIX}"
    return symbol

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate basic technical indicators"""
    df = df.copy()
    # Simple Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20, min_periods=1).mean()
    df['SMA_50'] = df['Close'].rolling(window=50, min_periods=1).mean()

    # RSI (simple version)
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

def build_df_from_chart_json(j: dict) -> tuple[dict, pd.DataFrame]:
    """Parse Yahoo chart JSON to (meta-like info dict, DataFrame)."""
    try:
        chart = j.get('chart', {})
        if chart.get('error'):
            return {}, pd.DataFrame()
        results = chart.get('result')
        if not results:
            return {}, pd.DataFrame()
        r0 = results[0]
        ts = r0.get('timestamp', []) or []
        ind = r0.get('indicators', {}).get('quote', [{}])[0]
        opens = ind.get('open', [])
        highs = ind.get('high', [])
        lows = ind.get('low', [])
        closes = ind.get('close', [])
        vols = ind.get('volume', [])

        if not ts or not closes:
            return {}, pd.DataFrame()

        # Build DataFrame
        dt_idx = pd.to_datetime(ts, unit='s', utc=True).tz_convert(r0.get('meta', {}).get('exchangeTimezoneName', 'UTC'), nonexistent='shift_forward', ambiguous='NaT')
        df = pd.DataFrame({
            'Open': pd.Series(opens, index=dt_idx, dtype='float64'),
            'High': pd.Series(highs, index=dt_idx, dtype='float64'),
            'Low': pd.Series(lows, index=dt_idx, dtype='float64'),
            'Close': pd.Series(closes, index=dt_idx, dtype='float64'),
            'Volume': pd.Series(vols, index=dt_idx, dtype='float64')
        }).sort_index()

        # Clean NaNs if any entire rows are None
        df = df.dropna(how='all')

        meta = r0.get('meta', {}) or {}
        last_price = meta.get('regularMarketPrice') or (df['Close'].iloc[-1] if not df.empty else None)
        previous_close = meta.get('previousClose') or (df['Close'].iloc[-2] if len(df) > 1 else last_price)

        finfo_like = {
            'last_price': safe_float(last_price, 0.0),
            'previous_close': safe_float(previous_close, 0.0),
            'year_high': safe_float(df['High'].max() if not df.empty else 0.0, 0.0),
            'year_low': safe_float(df['Low'].min() if not df.empty else 0.0, 0.0),
            'market_cap': 0,
            'trailing_pe': 0,
            'last_volume': int(df['Volume'].iloc[-1]) if 'Volume' in df.columns and not df.empty and pd.notna(df['Volume'].iloc[-1]) else 0
        }
        return finfo_like, df
    except Exception:
        return {}, pd.DataFrame()

def fetch_via_yahoo_chart(ticker_symbol: str) -> tuple[dict, pd.DataFrame]:
    """Direct call to Yahoo chart API with UA + Referer. Returns (info, DataFrame)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?range=6mo&interval=1d&includePrePost=false&events=div%2Csplits&corsDomain=finance.yahoo.com"
    headers = {
        "Referer": f"https://finance.yahoo.com/quote/{ticker_symbol}",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": session.headers.get("User-Agent", "")
    }
    try:
        r = session.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            app.logger.warning("chart API %s status=%s", ticker_symbol, r.status_code)
            return {}, pd.DataFrame()
        try:
            j = r.json()
        except JSONDecodeError:
            # Not JSON (blocked/HTML)
            app.logger.warning("chart API JSON decode failed for %s", ticker_symbol)
            return {}, pd.DataFrame()
        return build_df_from_chart_json(j)
    except Exception as e:
        app.logger.warning("chart API request failed for %s: %s", ticker_symbol, e)
        return {}, pd.DataFrame()

def fetch_stock_data(ticker_symbol: str):
    """Return (info dict, history DataFrame) with multiple fallbacks."""
    # 1) yfinance fast_info + history
    t = yf.Ticker(ticker_symbol, session=session)
    finfo = {}
    hist = pd.DataFrame()

    try:
        finfo = t.fast_info or {}
    except Exception as e:
        app.logger.warning("fast_info failed %s: %s", ticker_symbol, e)

    try:
        hist = t.history(period="6mo", interval="1d", auto_adjust=False, actions=False)
    except Exception as e:
        app.logger.warning("history() failed %s: %s", ticker_symbol, e)

    # 2) If history empty, try Yahoo chart API directly
    if hist is None or hist.empty:
        finfo_chart, hist_chart = fetch_via_yahoo_chart(ticker_symbol)
        if not (hist_chart is None or hist_chart.empty):
            # Merge finfo if fast_info is empty/partial
            merged = dict(finfo_chart)
            merged.update({k: v for k, v in finfo.items() if v is not None})
            return merged, hist_chart

    # 3) If still empty, try yf.download as a last resort
    if hist is None or hist.empty:
        try:
            dl = yf.download(
                tickers=ticker_symbol,
                period="6mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                session=session
            )
            if isinstance(dl, pd.DataFrame) and not dl.empty:
                if isinstance(dl.columns, pd.MultiIndex):
                    dl.columns = [c[-1] for c in dl.columns]
                hist = dl
        except Exception as e:
            app.logger.warning("yf.download failed %s: %s", ticker_symbol, e)

    return finfo or {}, hist if isinstance(hist, pd.DataFrame) else pd.DataFrame()

# ---------- API ----------
@app.route('/api/search/<symbol>')
def search_stock(symbol):
    """Search for stock information with robust Yahoo fallbacks"""
    try:
        sym = (symbol or "").upper().strip()
        # Try NSE, then BSE
        exchange_used = "NSE"
        ticker = get_indian_stock_ticker(sym, 'NSE')
        finfo, hist = fetch_stock_data(ticker)

        if hist is None or hist.empty:
            exchange_used = "BSE"
            ticker = get_indian_stock_ticker(sym, 'BSE')
            finfo, hist = fetch_stock_data(ticker)

        if hist is None or hist.empty:
            return jsonify({'error': 'Stock not found or no data available'}), 404

        # Indicators
        hist = calculate_technical_indicators(hist)

        # Prices (robust)
        last_close = safe_float(hist['Close'].iloc[-1], 0.0)
        prev_close_hist = safe_float(hist['Close'].iloc[-2], last_close) if len(hist) > 1 else last_close
        current_price = safe_float(finfo.get('last_price'), last_close)
        previous_close = safe_float(
            finfo.get('previous_close') or finfo.get('regularMarketPreviousClose'),
            prev_close_hist
        )
        change = current_price - previous_close
        change_percent = (change / previous_close * 100.0) if previous_close else 0.0

        # Volume and misc
        vol = finfo.get('last_volume')
        if vol is None:
            vol = int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns and pd.notna(hist['Volume'].iloc[-1]) else 0

        week_52_high = safe_float(finfo.get('year_high'), safe_float(hist['High'].max(), last_close))
        week_52_low = safe_float(finfo.get('year_low'), safe_float(hist['Low'].min(), last_close))
        market_cap = int(finfo.get('market_cap') or 0)
        pe_ratio = safe_float(finfo.get('trailing_pe'), 0.0)

        # Last 60 rows with Date column
        hist_tail = hist.tail(60).reset_index()
        if 'Date' not in hist_tail.columns:
            idx_name = hist_tail.columns[0]
            hist_tail = hist_tail.rename(columns={idx_name: 'Date'})
        if pd.api.types.is_datetime64_any_dtype(hist_tail['Date']):
            hist_tail['Date'] = hist_tail['Date'].dt.strftime('%Y-%m-%d')
        else:
            hist_tail['Date'] = hist_tail['Date'].astype(str)

        response = {
            'symbol': sym,
            'exchange': exchange_used,
            'name': sym,  # avoid .info
            'current_price': current_price,
            'previous_close': previous_close,
            'change': change,
            'change_percent': change_percent,
            'volume': int(vol),
            'market_cap': market_cap,
            'pe_ratio': pe_ratio,
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
    """Get stock recommendations based on user profile without using .info"""
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
                ticker = get_indian_stock_ticker(sym, 'NSE')
                finfo, hist = fetch_stock_data(ticker)
                if hist is None or hist.empty:
                    ticker = get_indian_stock_ticker(sym, 'BSE')
                    finfo, hist = fetch_stock_data(ticker)
                    if hist is None or hist.empty:
                        continue

                hist = calculate_technical_indicators(hist)
                current_price = safe_float(finfo.get('last_price'), safe_float(hist['Close'].iloc[-1], 0.0))

                if current_price <= 0 or current_price > budget:
                    continue

                recommendation = get_stock_recommendation(hist, user_profile)

                if recommendation['score'] >= 40:
                    recommendations.append({
                        'symbol': sym,
                        'name': sym,
                        'current_price': current_price,
                        'recommendation': recommendation,
                        'shares_affordable': int(budget / current_price)
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

# Debug endpoint to see what Yahoo returns from Render
@app.route('/api/debug/chart/<symbol>')
def debug_chart(symbol):
    sym = (symbol or "").upper().strip()
    ticker = get_indian_stock_ticker(sym, 'NSE')
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=6mo&interval=1d"
    try:
        r = session.get(url, headers={"Referer": f"https://finance.yahoo.com/quote/{ticker}"}, timeout=12)
        snippet = r.text[:200].replace("\n", " ")
        ct = r.headers.get("content-type", "")
        return jsonify({
            "ticker": ticker,
            "status": r.status_code,
            "content_type": ct,
            "is_json": "json" in ct.lower(),
            "snippet": snippet
        })
    except Exception as e:
        return jsonify({"error": str(e), "ticker": ticker}), 500

if __name__ == '__main__':
    # Render provides PORT; bind to 0.0.0.0
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
