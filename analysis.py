import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np

def get_market_signal(symbol="BTC/USDT", timeframe="15m"):
    """
    Áp dụng Logic Gia tốc (Physics Momentum) để tìm tín hiệu.
    """
    exchange = ccxt.binance() # Public API
    try:
        # 1. Fetch Data
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 2. Indicators (RSI, BB)
        df['rsi'] = df.ta.rsi(length=14)
        bb = df.ta.bbands(length=20, std=2)
        df = pd.concat([df, bb], axis=1)
        
        # 3. Physics Logic (Acceleration)
        # Vận tốc: SMA(Delta, 3)
        df['delta'] = df['close'].diff()
        df['velocity'] = df['delta'].rolling(window=3).mean()
        # Gia tốc: Vận tốc hiện tại trừ Vận tốc trước đó
        df['accel'] = df['velocity'].diff()
        
        # Lấy nến đóng cửa gần nhất (Không cần nến đang chạy)
        last = df.iloc[-2] # Lấy nến vừa đóng cửa
        close = last['close']
        rsi = last['rsi']
        accel = last['accel']
        lower_band = last['BBL_20_2.0']
        upper_band = last['BBU_20_2.0']
        
        # 4. Signal Logic
        signal = "NEUTRAL"
        
        # LONG: RSI < 30 + Giá < LowerBand + Gia tốc Dương (Đà giảm yếu đi)
        if rsi < 30 and close < lower_band and accel > 0:
            signal = "BUY"
            
        # SHORT: RSI > 70 + Giá > UpperBand + Gia tốc Âm (Đà tăng yếu đi)
        elif rsi > 70 and close > upper_band and accel < 0:
            signal = "SELL"
            
        return signal, close, f"RSI:{rsi:.1f}|Accel:{accel:.4f}"
        
    except Exception as e:
        print(f"Error fetching data or calculating: {e}")
        return "ERROR", 0, str(e)
