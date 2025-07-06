import yfinance as yf

def get_option_data(ticker, expiry, option_type, strike_price):
    """Fetch the option chain data from yfinance for the given ticker and strike."""
    options = yf.Ticker(ticker).options
    if expiry not in options:
        print(f"Expiry {expiry} not available for {ticker}.")
        return None
    option_chain = yf.Ticker(ticker).option_chain(expiry)
    if option_type == 'put':
        return option_chain.puts[option_chain.puts['strike'] == strike_price]
    elif option_type == 'call':
        return option_chain.calls[option_chain.calls['strike'] == strike_price]

def sell_cash_secured_put(ticker, strike_price, expiry):
    """Sell a cash-secured put and return premium."""
    option_data = get_option_data(ticker, expiry, 'put', strike_price)
    if option_data is not None and not option_data.empty:
        premium = option_data['lastPrice'].iloc[0]
        return premium  # Return the premium collected
    else:
        return None
