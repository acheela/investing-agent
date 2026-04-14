import yfinance as yf
import time
from datetime import date, datetime
from database import (
    get_portfolio, get_positions, execute_buy, execute_sell,
    save_portfolio_snapshot, get_portfolio_history, get_transactions
)

STARTING_CASH = 1000.0

# Simple in-memory quote cache: {ticker: (quote_dict, timestamp)}
_quote_cache: dict = {}
CACHE_TTL = 300  # seconds (5 minutes)


def get_quote(ticker: str) -> dict:
    """Fetch end-of-day quote for a ticker. Uses lightweight history() call. Caches 5 min."""
    ticker = ticker.upper()
    cached = _quote_cache.get(ticker)
    if cached:
        quote, ts = cached
        if time.time() - ts < CACHE_TTL:
            return quote

    try:
        t = yf.Ticker(ticker)

        # Use history - much lighter than .info, far less rate-limited
        hist = t.history(period="5d")
        if hist.empty:
            return {"error": f"Ticker '{ticker}' not found or no data available"}

        price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
        change = round(price - prev_close, 4)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0

        # Get name from fast_info (single lightweight call, won't rate limit)
        try:
            name = t.fast_info.get("longName") or ticker
        except Exception:
            name = ticker

        result = {
            "ticker": ticker,
            "name": name,
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "change": change,
            "change_pct": change_pct,
            "currency": "USD",
        }
        _quote_cache[ticker] = (result, time.time())
        return result

    except Exception as e:
        err = str(e)
        if "rate" in err.lower() or "429" in err:
            return {"error": "Yahoo Finance rate limit - wait 30 seconds and try again"}
        return {"error": f"Could not fetch {ticker}: {err}"}


def get_portfolio_state() -> dict:
    """Return full portfolio state: cash, positions with current values, totals."""
    portfolio = get_portfolio()
    cash = portfolio["cash"]
    positions = get_positions()

    enriched = []
    positions_value = 0.0

    for pos in positions:
        ticker = pos["ticker"]
        quote = get_quote(ticker)
        if "error" in quote:
            current_price = pos["avg_cost"]
        else:
            current_price = quote["price"]

        market_value = pos["shares"] * current_price
        cost_basis = pos["shares"] * pos["avg_cost"]
        gain = market_value - cost_basis
        gain_pct = round((gain / cost_basis) * 100, 2) if cost_basis else 0.0
        positions_value += market_value

        enriched.append({
            **pos,
            "current_price": round(current_price, 4),
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "gain": round(gain, 2),
            "gain_pct": gain_pct,
            "name": quote.get("name", ticker),
            "change": quote.get("change", 0),
            "change_pct": quote.get("change_pct", 0),
        })

    total_value = cash + positions_value
    total_gain = total_value - STARTING_CASH
    total_return_pct = round((total_gain / STARTING_CASH) * 100, 2)

    # Snapshot today's value
    today = date.today().isoformat()
    save_portfolio_snapshot(today, round(total_value, 2), round(cash, 2), round(positions_value, 2))

    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_gain": round(total_gain, 2),
        "total_return_pct": total_return_pct,
        "starting_cash": STARTING_CASH,
        "positions": enriched,
    }


def buy_stock(ticker: str, amount_usd: float) -> dict:
    """Buy $amount_usd worth of ticker at current price."""
    portfolio = get_portfolio()
    cash = portfolio["cash"]

    if amount_usd <= 0:
        return {"error": "Amount must be positive"}
    if amount_usd > cash:
        return {"error": f"Insufficient cash. Available: ${cash:.2f}"}

    quote = get_quote(ticker)
    if "error" in quote:
        return {"error": quote["error"]}

    price = quote["price"]
    shares = amount_usd / price

    execute_buy(ticker.upper(), shares, price)

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "shares": round(shares, 6),
        "price": price,
        "total": round(amount_usd, 2),
        "name": quote.get("name", ticker),
    }


def sell_stock(ticker: str, shares: float) -> dict:
    """Sell a specific number of shares of ticker."""
    from database import get_conn
    conn = get_conn()
    pos = conn.execute("SELECT * FROM positions WHERE ticker=?", (ticker.upper(),)).fetchone()
    conn.close()

    if not pos:
        return {"error": f"No position in {ticker}"}
    if shares > pos["shares"]:
        return {"error": f"You only own {pos['shares']:.6f} shares of {ticker}"}

    quote = get_quote(ticker)
    if "error" in quote:
        return {"error": quote["error"]}

    price = quote["price"]
    execute_sell(ticker.upper(), shares, price)

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "shares": shares,
        "price": price,
        "total": round(shares * price, 2),
    }


def sell_stock_usd(ticker: str, amount_usd: float) -> dict:
    """Sell $amount_usd worth of ticker."""
    quote = get_quote(ticker)
    if "error" in quote:
        return {"error": quote["error"]}
    price = quote["price"]
    shares = amount_usd / price
    return sell_stock(ticker, shares)


def _range_to_days(range_str: str) -> int:
    from datetime import date as d
    today = d.today()
    mapping = {
        "1d": 1,
        "1w": 7,
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "1y": 365,
        "5y": 1825,
    }
    if range_str == "ytd":
        return (today - today.replace(month=1, day=1)).days + 1
    return mapping.get(range_str, 90)


def portfolio_chart_data(range_str: str = "3m") -> dict:
    """Return history formatted for Chart.js, filtered by range."""
    days = _range_to_days(range_str)
    history = get_portfolio_history(days)
    if not history:
        today = date.today().isoformat()
        return {
            "labels": [today],
            "values": [STARTING_CASH],
            "range": range_str,
        }
    return {
        "labels": [h["date"] for h in history],
        "values": [h["total_value"] for h in history],
        "range": range_str,
    }
