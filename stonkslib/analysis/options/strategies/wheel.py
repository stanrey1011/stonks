from .puts.sell.cash_secured_put import sell_cash_secured_put
from .calls.sell.covered_call import sell_covered_call
import yfinance as yf

def execute_wheel_strategy(ticker, put_strike, call_strike, expiry, shares_owned=100):
    # Step 1: Sell Cash-Secured Put
    premium_put = sell_cash_secured_put(ticker, put_strike, expiry)
    if premium_put:
        print(f"Sold Cash-Secured Put on {ticker} at ${put_strike} for a premium of ${premium_put}")
    
    # Step 2: Check if assigned (i.e., the stock price falls below the put strike price)
    stock = yf.Ticker(ticker)
    current_price = stock.history(period="1d")['Close'].iloc[0]
    if current_price < put_strike:
        print(f"Assigned {ticker} stock at ${put_strike} due to current price {current_price}")

        # Step 3: Sell Covered Call after assignment
        premium_call = sell_covered_call(ticker, call_strike, expiry, shares_owned)
        if premium_call:
            print(f"Sold Covered Call on {ticker} at ${call_strike} for a premium of ${premium_call}")
    else:
        print(f"No assignment. {ticker} current price {current_price} is above strike {put_strike}")
