from flask_socketio import SocketIO, emit
import yfinance as yf
import threading
import time

socketio = SocketIO(cors_allowed_origins="*")

def init_socketio(app):
    socketio.init_app(app)
    return socketio

@socketio.on('subscribe')
def handle_subscription(data):
    symbol = data['symbol']
    
    def emit_price_updates():
        while True:
            try:
                ticker = get_indian_stock_ticker(symbol, 'NSE')
                stock = yf.Ticker(ticker)
                info = stock.info
                
                emit('price_update', {
                    'symbol': symbol,
                    'price': info.get('regularMarketPrice', 0),
                    'change': info.get('regularMarketChange', 0),
                    'changePercent': info.get('regularMarketChangePercent', 0),
                    'volume': info.get('volume', 0)
                })
                
                time.sleep(5)  # Update every 5 seconds
            except:
                break
    
    thread = threading.Thread(target=emit_price_updates)
    thread.daemon = True
    thread.start()
