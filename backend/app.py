import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
from config import Config

# Paths to frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

# Serve frontend from Flask to avoid CORS
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config.from_object(Config)
# You can scope CORS to API only
CORS(app, resources={r"/api/*": {"origins": "*"}})

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

def calculate_technical_indicators(df):
    """Calculate basic technical indicators"""
    # Simple Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands
    df['BB_middle'] = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
    df['BB_lower'] = df['BB_middle'] - (bb_std * 2)
    
    return df

def get_stock_recommendation(stock_data, user_profile):
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
    if 30 < latest['RSI'] < 70:
        score += 20
        reasons.append(f"RSI at {latest['RSI']:.2f} - Normal range")
    elif latest['RSI'] <= 30:
        score += 25
        reasons.append(f"RSI at {latest['RSI']:.2f} - Oversold (Potential buy)")
    
    # Bollinger Bands
    if latest['Close'] < latest['BB_lower']:
        score += 20
        reasons.append("Price below lower Bollinger Band (Oversold)")
    
    # Volume analysis
    avg_volume = stock_data['Volume'].rolling(window=20).mean().iloc[-1]
    if latest['Volume'] > avg_volume * 1.5:
        score += 15
        reasons.append("High volume activity")
    
    # Risk assessment
    volatility = stock_data['Close'].pct_change().std() * np.sqrt(252) * 100
    risk_level = "Low" if volatility < 20 else "Medium" if volatility < 40 else "High"
    
    # Match with user profile
    risk_match = True
    if user_profile.get('risk_tolerance') == 'low' and risk_level == 'High':
        risk_match = False
        score -= 30
    
    recommendation = {
        'score': score,
        'rating': 'Strong Buy' if score >= 70 else 'Buy' if score >= 50 else 'Hold' if score >= 30 else 'Sell',
        'reasons': reasons,
        'risk_level': risk_level,
        'volatility': volatility,
        'risk_match': risk_match
    }
    
    return recommendation

# ---------- API ----------
@app.route('/api/search/<symbol>')
def search_stock(symbol):
    """Search for stock information"""
    try:
        # Try NSE first, then BSE
        ticker_nse = get_indian_stock_ticker(symbol, 'NSE')
        stock = yf.Ticker(ticker_nse)
        info = stock.info
        
        if not info.get('regularMarketPrice'):
            ticker_bse = get_indian_stock_ticker(symbol, 'BSE')
            stock = yf.Ticker(ticker_bse)
            info = stock.info
        
        # Get historical data
        hist = stock.history(period="3mo")
        
        if hist.empty:
            return jsonify({'error': 'Stock not found'}), 404
        
        # Calculate technical indicators
        hist = calculate_technical_indicators(hist)
        
        # Prepare response
        current_price = info.get('regularMarketPrice', hist['Close'].iloc[-1])
        prev_close = info.get('previousClose', hist['Close'].iloc[-2])
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        response = {
            'symbol': symbol,
            'name': info.get('longName', symbol),
            'current_price': current_price,
            'previous_close': prev_close,
            'change': change,
            'change_percent': change_percent,
            'volume': int(hist['Volume'].iloc[-1]),
            'market_cap': info.get('marketCap', 0),
            'pe_ratio': info.get('trailingPE', 0),
            'week_52_high': info.get('fiftyTwoWeekHigh', 0),
            'week_52_low': info.get('fiftyTwoWeekLow', 0),
            'historical_data': hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(60).to_dict('records')
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """Get stock recommendations based on user profile"""
    try:
        user_profile = request.json or {}
        budget = user_profile.get('budget', 100000)
        risk_tolerance = user_profile.get('risk_tolerance', 'medium')  # kept for compatibility
        
        # Popular Indian stocks for screening
        stocks_to_analyze = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR',
            'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'LT',
            'HCLTECH', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'TITAN'
        ]
        
        recommendations = []
        
        for symbol in stocks_to_analyze:
            try:
                ticker = get_indian_stock_ticker(symbol, 'NSE')
                stock = yf.Ticker(ticker)
                hist = stock.history(period="3mo")
                
                if hist.empty:
                    continue
                
                hist = calculate_technical_indicators(hist)
                info = stock.info
                current_price = info.get('regularMarketPrice', hist['Close'].iloc[-1])
                
                # Skip if price is above budget
                if current_price > budget:
                    continue
                
                recommendation = get_stock_recommendation(hist, user_profile)
                
                if recommendation['score'] >= 40:  # Only include promising stocks
                    recommendations.append({
                        'symbol': symbol,
                        'name': info.get('longName', symbol),
                        'current_price': current_price,
                        'recommendation': recommendation,
                        'shares_affordable': int(budget / current_price)
                    })
            
            except Exception:
                continue
        
        # Sort by score
        recommendations.sort(key=lambda x: x['recommendation']['score'], reverse=True)
        
        return jsonify(recommendations[:10])  # Return top 10
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    # Render provides PORT; bind to 0.0.0.0
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
