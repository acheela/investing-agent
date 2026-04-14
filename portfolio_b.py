"""Builder portfolio - completely separate from the main portfolio tab."""
import time
from datetime import date
from portfolio import get_quote, _quote_cache, CACHE_TTL  # reuse quote logic + cache
from database import (
    get_portfolio_b, get_positions_b, execute_buy_b, execute_sell_b,
    save_portfolio_snapshot_b, get_portfolio_history_b, get_transactions_b
)

STARTING_CASH_B = 1000.0


def get_portfolio_state_b() -> dict:
    portfolio = get_portfolio_b()
    cash = portfolio["cash"]
    positions = get_positions_b()
    enriched = []
    positions_value = 0.0

    for pos in positions:
        ticker = pos["ticker"]
        quote = get_quote(ticker)
        current_price = quote.get("price", pos["avg_cost"]) if "error" not in quote else pos["avg_cost"]
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
    total_gain = total_value - STARTING_CASH_B
    total_return_pct = round((total_gain / STARTING_CASH_B) * 100, 2)

    today = date.today().isoformat()
    save_portfolio_snapshot_b(today, round(total_value, 2), round(cash, 2), round(positions_value, 2))

    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_gain": round(total_gain, 2),
        "total_return_pct": total_return_pct,
        "starting_cash": STARTING_CASH_B,
        "positions": enriched,
    }


def buy_stock_b(ticker: str, amount_usd: float) -> dict:
    portfolio = get_portfolio_b()
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
    execute_buy_b(ticker.upper(), shares, price)
    return {"ok": True, "ticker": ticker.upper(), "shares": round(shares, 6), "price": price, "total": round(amount_usd, 2), "name": quote.get("name", ticker)}


def sell_stock_b(ticker: str, shares: float) -> dict:
    from database import get_conn
    conn = get_conn()
    pos = conn.execute("SELECT * FROM positions_b WHERE ticker=?", (ticker.upper(),)).fetchone()
    conn.close()
    if not pos:
        return {"error": f"No position in {ticker}"}
    if shares > pos["shares"]:
        return {"error": f"You only own {pos['shares']:.6f} shares of {ticker}"}
    quote = get_quote(ticker)
    if "error" in quote:
        return {"error": quote["error"]}
    price = quote["price"]
    execute_sell_b(ticker.upper(), shares, price)
    return {"ok": True, "ticker": ticker.upper(), "shares": shares, "price": price, "total": round(shares * price, 2)}


def sell_stock_usd_b(ticker: str, amount_usd: float) -> dict:
    quote = get_quote(ticker)
    if "error" in quote:
        return {"error": quote["error"]}
    shares = amount_usd / quote["price"]
    return sell_stock_b(ticker, shares)


def _range_to_days_b(range_str: str) -> int:
    from datetime import date as d
    today = d.today()
    mapping = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365, "5y": 1825}
    if range_str == "ytd":
        return (today - today.replace(month=1, day=1)).days + 1
    return mapping.get(range_str, 90)


def portfolio_chart_data_b(range_str: str = "3m") -> dict:
    days = _range_to_days_b(range_str)
    history = get_portfolio_history_b(days)
    if not history:
        today = date.today().isoformat()
        return {"labels": [today], "values": [STARTING_CASH_B], "range": range_str}
    return {"labels": [h["date"] for h in history], "values": [h["total_value"] for h in history], "range": range_str}
