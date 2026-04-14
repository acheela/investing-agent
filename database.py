import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "investing_agent.db"

DEFAULT_SOURCES = [
    # Substack
    {"type": "substack", "name": "Citrini Research", "handle": "citriniresearch", "url": "https://citriniresearch.substack.com/feed", "active": True},
    {"type": "substack", "name": "Doomberg", "handle": "doomberg", "url": "https://doomberg.substack.com/feed", "active": True},
    {"type": "substack", "name": "Net Interest (Marc Rubinstein)", "handle": "netinterest", "url": "https://netinterest.substack.com/feed", "active": True},
    {"type": "substack", "name": "Kyla Scanlon", "handle": "kylascanlon", "url": "https://kylascanlon.substack.com/feed", "active": True},
    {"type": "substack", "name": "The Bear Cave", "handle": "thebearcave", "url": "https://thebearcave.substack.com/feed", "active": True},
    {"type": "substack", "name": "Kuppy (Adventures in Capitalism)", "handle": "adventuresincapitalism", "url": "https://adventuresincapitalism.substack.com/feed", "active": True},
    # Twitter/X accounts
    {"type": "twitter", "name": "Citrini Research", "handle": "@citriniresearch", "url": "https://twitter.com/citriniresearch", "active": True},
    {"type": "twitter", "name": "Borrowed Ideas (Samir Varma)", "handle": "@borrowed_ideas", "url": "https://twitter.com/borrowed_ideas", "active": True},
    {"type": "twitter", "name": "Jesse Felder", "handle": "@jessefelder", "url": "https://twitter.com/jessefelder", "active": True},
    {"type": "twitter", "name": "Meb Faber", "handle": "@MebFaber", "url": "https://twitter.com/MebFaber", "active": True},
    {"type": "twitter", "name": "Chris Mayer", "handle": "@chriswmayer", "url": "https://twitter.com/chriswmayer", "active": True},
    {"type": "twitter", "name": "Gavin Baker (Atreides)", "handle": "@GavinSBaker", "url": "https://twitter.com/GavinSBaker", "active": True},
    # YouTube / Podcasts
    {"type": "youtube", "name": "Invest Like the Best", "handle": "InvestLikeTheBest", "url": "https://www.youtube.com/@investlikethebest", "active": True},
    {"type": "youtube", "name": "Acquired Podcast", "handle": "AcquiredFM", "url": "https://www.youtube.com/@AcquiredFM", "active": True},
    {"type": "youtube", "name": "We Study Billionaires", "handle": "TheInvestorsPodcast", "url": "https://www.youtube.com/@TheInvestorsPodcast", "active": True},
    {"type": "youtube", "name": "Capital Allocators", "handle": "CapitalAllocators", "url": "https://www.youtube.com/@CapitalAllocators", "active": True},
    {"type": "youtube", "name": "Founders Podcast", "handle": "FoundersPodcast", "url": "https://www.youtube.com/@FoundersPodcast", "active": True},
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            handle TEXT NOT NULL,
            url TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            title TEXT,
            url TEXT UNIQUE,
            content TEXT,
            published_at TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            ticker TEXT,
            direction TEXT,
            buffett_take TEXT,
            greenblatt_take TEXT,
            soros_take TEXT,
            simons_take TEXT,
            conviction_score REAL,
            summary TEXT,
            raw_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(article_id) REFERENCES articles(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS source_track_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            ticker TEXT,
            call_direction TEXT,
            call_date TEXT,
            outcome TEXT,
            return_pct REAL,
            notes TEXT,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        )
    """)

    # Seed default sources if empty
    c.execute("SELECT COUNT(*) FROM sources")
    if c.fetchone()[0] == 0:
        for s in DEFAULT_SOURCES:
            c.execute(
                "INSERT INTO sources (type, name, handle, url, active) VALUES (?, ?, ?, ?, ?)",
                (s["type"], s["name"], s["handle"], s["url"], 1 if s["active"] else 0)
            )

    # Portfolio tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            cash REAL NOT NULL DEFAULT 1000.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            shares REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            positions_value REAL NOT NULL
        )
    """)

    # Seed portfolio with $1000 if not exists
    c.execute("SELECT COUNT(*) FROM portfolio")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO portfolio (id, cash) VALUES (1, 1000.0)")

    # Builder portfolio tables (separate from main portfolio)
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_b (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            cash REAL NOT NULL DEFAULT 1000.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions_b (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            shares REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions_b (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_history_b (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            positions_value REAL NOT NULL
        )
    """)
    c.execute("SELECT COUNT(*) FROM portfolio_b")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO portfolio_b (id, cash) VALUES (1, 1000.0)")

    # Builder tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS builder_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT,
            url TEXT,
            checked INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS builder_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            thesis TEXT,
            stocks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_all_sources():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sources ORDER BY type, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_sources(source_type=None):
    conn = get_conn()
    if source_type:
        rows = conn.execute("SELECT * FROM sources WHERE active=1 AND type=?", (source_type,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sources WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_source(type_, name, handle, url):
    conn = get_conn()
    conn.execute(
        "INSERT INTO sources (type, name, handle, url, active) VALUES (?, ?, ?, ?, 1)",
        (type_, name, handle, url)
    )
    conn.commit()
    conn.close()


def toggle_source(source_id, active):
    conn = get_conn()
    conn.execute("UPDATE sources SET active=? WHERE id=?", (1 if active else 0, source_id))
    conn.commit()
    conn.close()


def delete_source(source_id):
    conn = get_conn()
    conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


def save_article(source_id, title, url, content, published_at):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO articles (source_id, title, url, content, published_at) VALUES (?, ?, ?, ?, ?)",
            (source_id, title, url, content, published_at)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM articles WHERE url=?", (url,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_recent_articles(limit=50):
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, s.name as source_name, s.type as source_type
        FROM articles a
        JOIN sources s ON a.source_id = s.id
        ORDER BY a.fetched_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_signal(article_id, ticker, direction, buffett, greenblatt, soros, simons, conviction, summary, raw):
    conn = get_conn()
    conn.execute("""
        INSERT INTO signals
        (article_id, ticker, direction, buffett_take, greenblatt_take, soros_take, simons_take, conviction_score, summary, raw_analysis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (article_id, ticker, direction, buffett, greenblatt, soros, simons, conviction, summary, raw))
    conn.commit()
    conn.close()


def get_recent_signals(limit=30):
    conn = get_conn()
    rows = conn.execute("""
        SELECT sg.*, a.title as article_title, a.url as article_url, s.name as source_name
        FROM signals sg
        JOIN articles a ON sg.article_id = a.id
        JOIN sources s ON a.source_id = s.id
        ORDER BY sg.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Portfolio ---

def get_portfolio():
    conn = get_conn()
    row = conn.execute("SELECT * FROM portfolio WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {"cash": 1000.0}


def get_positions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM positions WHERE shares > 0 ORDER BY ticker").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transactions(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY executed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute_buy(ticker, shares, price):
    total = shares * price
    conn = get_conn()
    try:
        # Deduct cash
        conn.execute("UPDATE portfolio SET cash = cash - ? WHERE id=1", (total,))
        # Upsert position with updated avg cost
        existing = conn.execute("SELECT * FROM positions WHERE ticker=?", (ticker,)).fetchone()
        if existing:
            new_shares = existing["shares"] + shares
            new_avg = (existing["shares"] * existing["avg_cost"] + total) / new_shares
            conn.execute(
                "UPDATE positions SET shares=?, avg_cost=? WHERE ticker=?",
                (new_shares, new_avg, ticker)
            )
        else:
            conn.execute(
                "INSERT INTO positions (ticker, shares, avg_cost) VALUES (?, ?, ?)",
                (ticker, shares, price)
            )
        conn.execute(
            "INSERT INTO transactions (ticker, action, shares, price, total) VALUES (?, 'buy', ?, ?, ?)",
            (ticker, shares, price, total)
        )
        conn.commit()
    finally:
        conn.close()


def execute_sell(ticker, shares, price):
    total = shares * price
    conn = get_conn()
    try:
        conn.execute("UPDATE portfolio SET cash = cash + ? WHERE id=1", (total,))
        existing = conn.execute("SELECT * FROM positions WHERE ticker=?", (ticker,)).fetchone()
        if existing:
            new_shares = existing["shares"] - shares
            if new_shares <= 0:
                conn.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
            else:
                conn.execute("UPDATE positions SET shares=? WHERE ticker=?", (new_shares, ticker))
        conn.execute(
            "INSERT INTO transactions (ticker, action, shares, price, total) VALUES (?, 'sell', ?, ?, ?)",
            (ticker, shares, price, total)
        )
        conn.commit()
    finally:
        conn.close()


def save_portfolio_snapshot(date_str, total_value, cash, positions_value):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO portfolio_history (date, total_value, cash, positions_value)
        VALUES (?, ?, ?, ?)
    """, (date_str, total_value, cash, positions_value))
    conn.commit()
    conn.close()


def get_portfolio_history(days=90):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM portfolio_history
        ORDER BY date DESC LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


# --- Builder ---

def add_builder_source(type_, name, content, url=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO builder_sources (type, name, content, url, checked) VALUES (?, ?, ?, ?, 1)",
        (type_, name, content, url)
    )
    conn.commit()
    conn.close()


def get_builder_sources():
    conn = get_conn()
    rows = conn.execute("SELECT id, type, name, url, checked, created_at FROM builder_sources ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_builder_source(source_id, checked):
    conn = get_conn()
    conn.execute("UPDATE builder_sources SET checked=? WHERE id=?", (1 if checked else 0, source_id))
    conn.commit()
    conn.close()


def delete_builder_source(source_id):
    conn = get_conn()
    conn.execute("DELETE FROM builder_sources WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


def clear_builder_sources():
    conn = get_conn()
    conn.execute("DELETE FROM builder_sources")
    conn.commit()
    conn.close()


def get_builder_source_content(source_id):
    conn = get_conn()
    row = conn.execute("SELECT content FROM builder_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    return row["content"] if row else ""


def get_checked_builder_content():
    conn = get_conn()
    rows = conn.execute("SELECT name, content FROM builder_sources WHERE checked=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_builder_ideas(ideas: list):
    import json
    conn = get_conn()
    conn.execute("DELETE FROM builder_ideas")
    for idea in ideas:
        conn.execute(
            "INSERT INTO builder_ideas (title, thesis, stocks) VALUES (?, ?, ?)",
            (idea.get("title", ""), idea.get("thesis", ""), json.dumps(idea.get("stocks", [])))
        )
    conn.commit()
    conn.close()


def get_builder_ideas():
    import json
    conn = get_conn()
    rows = conn.execute("SELECT * FROM builder_ideas ORDER BY id").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["stocks"] = json.loads(d["stocks"])
        except Exception:
            d["stocks"] = []
        result.append(d)
    return result


# --- Builder Portfolio (separate from main portfolio) ---

def get_portfolio_b():
    conn = get_conn()
    row = conn.execute("SELECT * FROM portfolio_b WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {"cash": 1000.0}


def get_positions_b():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM positions_b WHERE shares > 0 ORDER BY ticker").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transactions_b(limit=100):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM transactions_b ORDER BY executed_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute_buy_b(ticker, shares, price):
    total = shares * price
    conn = get_conn()
    try:
        conn.execute("UPDATE portfolio_b SET cash = cash - ? WHERE id=1", (total,))
        existing = conn.execute("SELECT * FROM positions_b WHERE ticker=?", (ticker,)).fetchone()
        if existing:
            new_shares = existing["shares"] + shares
            new_avg = (existing["shares"] * existing["avg_cost"] + total) / new_shares
            conn.execute("UPDATE positions_b SET shares=?, avg_cost=? WHERE ticker=?", (new_shares, new_avg, ticker))
        else:
            conn.execute("INSERT INTO positions_b (ticker, shares, avg_cost) VALUES (?, ?, ?)", (ticker, shares, price))
        conn.execute("INSERT INTO transactions_b (ticker, action, shares, price, total) VALUES (?, 'buy', ?, ?, ?)", (ticker, shares, price, total))
        conn.commit()
    finally:
        conn.close()


def execute_sell_b(ticker, shares, price):
    total = shares * price
    conn = get_conn()
    try:
        conn.execute("UPDATE portfolio_b SET cash = cash + ? WHERE id=1", (total,))
        existing = conn.execute("SELECT * FROM positions_b WHERE ticker=?", (ticker,)).fetchone()
        if existing:
            new_shares = existing["shares"] - shares
            if new_shares <= 0:
                conn.execute("DELETE FROM positions_b WHERE ticker=?", (ticker,))
            else:
                conn.execute("UPDATE positions_b SET shares=? WHERE ticker=?", (new_shares, ticker))
        conn.execute("INSERT INTO transactions_b (ticker, action, shares, price, total) VALUES (?, 'sell', ?, ?, ?)", (ticker, shares, price, total))
        conn.commit()
    finally:
        conn.close()


def save_portfolio_snapshot_b(date_str, total_value, cash, positions_value):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO portfolio_history_b (date, total_value, cash, positions_value)
        VALUES (?, ?, ?, ?)
    """, (date_str, total_value, cash, positions_value))
    conn.commit()
    conn.close()


def get_portfolio_history_b(days=90):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM portfolio_history_b ORDER BY date DESC LIMIT ?", (days,)).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))
