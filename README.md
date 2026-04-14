# Investing Agent

A personal investing intelligence tool that monitors the writers, analysts, and investors you follow, runs their content through four legendary investor frameworks (Buffett, Greenblatt, Soros, Simons), and surfaces actionable trade signals. Includes a paper trading portfolio to test ideas risk-free and a Builder tab for uploading research PDFs or YouTube videos to generate thematic stock ideas.

## Features

- **Signal Analysis** - Fetches content from Substack, YouTube, and X sources you configure, then analyzes each piece through four investor lenses
- **Paper Trading** - $1,000 starting cash, buy/sell by dollar amount, live prices via Yahoo Finance, portfolio chart with full range selector
- **Builder** - Upload PDFs or paste YouTube links, check off sources, and generate thematic investment ideas with stock picks powered by Claude
- **Portfolio** - Independent $1,000 portfolio to test ideas from your research

## Stack

- Backend: FastAPI + SQLite
- AI: Anthropic Claude (claude-sonnet-4-6)
- Prices: yfinance
- Frontend: Vanilla JS + Chart.js

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
python main.py
```

Open http://localhost:8080
