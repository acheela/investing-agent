import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

load_dotenv()

from database import (
    init_db, get_all_sources, add_source, toggle_source, delete_source,
    get_recent_articles, get_recent_signals, get_transactions,
    add_builder_source, get_builder_sources, toggle_builder_source,
    delete_builder_source, clear_builder_sources, get_builder_ideas
)
from scrapers import fetch_all
from analyzer import analyze_batch
from portfolio import get_portfolio_state, get_quote, buy_stock, sell_stock, sell_stock_usd, portfolio_chart_data
from portfolio_b import get_portfolio_state_b, buy_stock_b, sell_stock_b, sell_stock_usd_b, portfolio_chart_data_b
from database import get_transactions_b
from builder import extract_pdf_text, fetch_youtube_title, fetch_youtube_transcript_text, generate_ideas

app = FastAPI(title="Investing Agent", version="1.0.0")

# Serve frontend static files
frontend_dir = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.on_event("startup")
async def startup():
    init_db()
    print("[server] Database initialized")


# --- Frontend ---

@app.get("/")
async def root():
    return FileResponse(str(frontend_dir / "index.html"))


# --- Sources ---

@app.get("/api/sources")
async def api_get_sources():
    return get_all_sources()


class SourceCreate(BaseModel):
    type: str   # substack | twitter | youtube
    name: str
    handle: str
    url: str


@app.post("/api/sources")
async def api_add_source(body: SourceCreate):
    if body.type not in ("substack", "twitter", "youtube"):
        raise HTTPException(400, "type must be substack, twitter, or youtube")
    add_source(body.type, body.name, body.handle, body.url)
    return {"ok": True}


class SourceToggle(BaseModel):
    active: bool


@app.patch("/api/sources/{source_id}")
async def api_toggle_source(source_id: int, body: SourceToggle):
    toggle_source(source_id, body.active)
    return {"ok": True}


@app.delete("/api/sources/{source_id}")
async def api_delete_source(source_id: int):
    delete_source(source_id)
    return {"ok": True}


# --- Fetch + Analyze ---

@app.post("/api/run")
async def api_run():
    """
    Fetch latest content from all active sources, run multi-lens analysis,
    and return new signals. DOES NOT execute any trades - review only.
    """
    articles = await fetch_all()
    if not articles:
        return {"message": "No new articles found", "signals": []}
    signals = await analyze_batch(articles)
    return {
        "message": f"Analyzed {len(articles)} articles, found {len(signals)} signals",
        "signals": signals,
        "articles_fetched": len(articles),
    }


# --- Articles & Signals ---

@app.get("/api/articles")
async def api_get_articles(limit: int = 50):
    return get_recent_articles(limit)


@app.get("/api/signals")
async def api_get_signals(limit: int = 30):
    return get_recent_signals(limit)


# --- Portfolio ---

@app.get("/api/portfolio")
async def api_get_portfolio():
    return get_portfolio_state()


@app.get("/api/portfolio/quote")
async def api_quote(ticker: str):
    result = get_quote(ticker)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/portfolio/chart")
async def api_portfolio_chart(range: str = "3m"):
    return portfolio_chart_data(range)


@app.get("/api/portfolio/transactions")
async def api_transactions(limit: int = 100):
    return get_transactions(limit)


class BuyOrder(BaseModel):
    ticker: str
    amount_usd: float   # dollar amount to invest


class SellOrder(BaseModel):
    ticker: str
    shares: float = 0.0
    amount_usd: float = 0.0   # sell by dollar amount OR shares


@app.post("/api/portfolio/buy")
async def api_buy(order: BuyOrder):
    result = buy_stock(order.ticker, order.amount_usd)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/portfolio/sell")
async def api_sell(order: SellOrder):
    if order.amount_usd > 0:
        result = sell_stock_usd(order.ticker, order.amount_usd)
    elif order.shares > 0:
        result = sell_stock(order.ticker, order.shares)
    else:
        raise HTTPException(400, "Provide shares or amount_usd")
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# --- Builder Portfolio (separate $1000 from main portfolio) ---

@app.get("/api/portfolio-b")
async def api_get_portfolio_b():
    return get_portfolio_state_b()


@app.get("/api/portfolio-b/chart")
async def api_portfolio_chart_b(range: str = "3m"):
    return portfolio_chart_data_b(range)


@app.get("/api/portfolio-b/transactions")
async def api_transactions_b(limit: int = 100):
    return get_transactions_b(limit)


@app.post("/api/portfolio-b/buy")
async def api_buy_b(order: BuyOrder):
    result = buy_stock_b(order.ticker, order.amount_usd)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/portfolio-b/sell")
async def api_sell_b(order: SellOrder):
    if order.amount_usd > 0:
        result = sell_stock_usd_b(order.ticker, order.amount_usd)
    elif order.shares > 0:
        result = sell_stock_b(order.ticker, order.shares)
    else:
        raise HTTPException(400, "Provide shares or amount_usd")
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# --- Builder ---

@app.post("/api/builder/upload-pdf")
async def api_upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted")
    data = await file.read()
    text = extract_pdf_text(data)
    name = file.filename.removesuffix(".pdf")[:50]
    add_builder_source("pdf", name, text)
    return {"ok": True, "name": name, "chars": len(text)}


class YouTubeLink(BaseModel):
    url: str


@app.post("/api/builder/add-youtube")
async def api_add_youtube(body: YouTubeLink):
    url = body.url.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(400, "Must be a YouTube URL")
    title = await fetch_youtube_title(url)
    transcript = await fetch_youtube_transcript_text(url)
    content = f"[YouTube] {title}\n\n{transcript}" if transcript else f"[YouTube] {title}"
    add_builder_source("youtube", title[:50], content, url)
    return {"ok": True, "name": title}


@app.get("/api/builder/sources")
async def api_builder_sources():
    return get_builder_sources()


class BuilderToggle(BaseModel):
    checked: bool


@app.patch("/api/builder/sources/{source_id}")
async def api_builder_toggle(source_id: int, body: BuilderToggle):
    toggle_builder_source(source_id, body.checked)
    return {"ok": True}


@app.delete("/api/builder/sources/{source_id}")
async def api_builder_delete(source_id: int):
    delete_builder_source(source_id)
    return {"ok": True}


@app.delete("/api/builder/sources")
async def api_builder_clear():
    clear_builder_sources()
    return {"ok": True}


@app.post("/api/builder/run")
async def api_builder_run():
    ideas = generate_ideas()
    return {"ok": True, "ideas": ideas, "count": len(ideas)}


@app.get("/api/builder/ideas")
async def api_builder_ideas():
    return get_builder_ideas()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
