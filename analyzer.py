import os
import json
import time
import anthropic
from database import save_signal

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an elite investment research analyst. You analyze content from top investors, operators, and market commentators to extract actionable investment signals.

Your job is to:
1. Identify specific investment signals (tickers, sectors, themes) mentioned
2. Evaluate each signal through four legendary investor lenses
3. Score conviction and synthesize a clear recommendation - but NEVER execute or suggest execution without human review

Always respond in valid JSON."""

INVESTOR_LENSES = {
    "buffett": """Warren Buffett lens: Focus on durable competitive moats, quality of management, long-term earnings power,
understandable businesses, and buying at a reasonable price. Ask: Is this a wonderful business at a fair price?
Would I be comfortable holding this for 10+ years? Is the moat widening or narrowing?""",

    "greenblatt": """Joel Greenblatt lens: Magic Formula thinking - high earnings yield (EBIT/EV) combined with high return on invested capital (ROIC).
Look for special situations: spin-offs, mergers, restructurings, bankruptcies.
Ask: Is the market mispricing this due to complexity or forced selling?""",

    "soros": """George Soros / macro lens: Reflexivity theory - markets and fundamentals influence each other in feedback loops.
Look for narrative shifts, positioning extremes, and macro regime changes.
Ask: Is there a prevailing misconception the market holds? Is there a catalyst that will force a re-rating?
What does positioning and flow of funds tell us?""",

    "simons": """Jim Simons / quantitative lens: Look for systematic, repeatable signals - anomalies, patterns, or data edges.
Ask: Is there a quantifiable edge here? Can this signal be backtested?
Is there a statistical pattern in how the market has historically responded to similar situations?""",
}


def build_analysis_prompt(article: dict) -> str:
    return f"""Analyze the following investment content and extract signals.

Source: {article.get('source_name', 'Unknown')}
Title: {article.get('title', '')}
Content: {article.get('content', '')}

---

For each investment signal you find, provide analysis through all four investor lenses.
If no clear investment signal exists, return an empty signals array.

Respond ONLY with this JSON structure:
{{
  "signals": [
    {{
      "ticker": "TICKER or 'MACRO:theme' or 'SECTOR:name'",
      "direction": "long" | "short" | "watch" | "avoid",
      "conviction": 1-10,
      "buffett": "1-2 sentence Buffett perspective",
      "greenblatt": "1-2 sentence Greenblatt perspective",
      "soros": "1-2 sentence Soros/macro perspective",
      "simons": "1-2 sentence Simons/quant perspective",
      "summary": "2-3 sentence plain-English synthesis of the signal and why it might be unpriced",
      "key_quote": "most relevant quote or phrase from the source content"
    }}
  ]
}}"""


async def analyze_article(article: dict) -> list[dict]:
    """
    Run multi-lens analysis on a single article.
    Returns list of signal dicts. Does NOT execute any trades.
    """
    if not article.get("content") or len(article["content"]) < 50:
        return []

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": build_analysis_prompt(article)}
            ]
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        signals = parsed.get("signals", [])

        for sig in signals:
            save_signal(
                article_id=article["article_id"],
                ticker=sig.get("ticker", ""),
                direction=sig.get("direction", "watch"),
                buffett=sig.get("buffett", ""),
                greenblatt=sig.get("greenblatt", ""),
                soros=sig.get("soros", ""),
                simons=sig.get("simons", ""),
                conviction=float(sig.get("conviction", 5)),
                summary=sig.get("summary", ""),
                raw=raw,
            )

        return signals

    except json.JSONDecodeError as e:
        print(f"[analyzer] JSON parse error for '{article.get('title')}': {e}")
        return []
    except anthropic.RateLimitError:
        print(f"[analyzer] Rate limited - waiting 20s before retrying '{article.get('title')}'")
        time.sleep(20)
        return []
    except anthropic.APIError as e:
        print(f"[analyzer] Anthropic API error: {e}")
        return []
    except Exception as e:
        print(f"[analyzer] Unexpected error: {e}")
        return []


# Max articles to analyze per run - prevents blowing through rate limits
MAX_PER_RUN = 10
# Seconds to wait between each API call
DELAY_BETWEEN_CALLS = 3.0


async def analyze_batch(articles: list[dict]) -> list[dict]:
    """
    Analyze a batch of articles with rate-limit-safe pacing.
    Caps at MAX_PER_RUN articles per run with DELAY_BETWEEN_CALLS seconds between each.
    """
    all_signals = []
    batch = articles[:MAX_PER_RUN]
    if len(articles) > MAX_PER_RUN:
        print(f"[analyzer] Capping batch at {MAX_PER_RUN} articles (got {len(articles)})")

    for i, article in enumerate(batch):
        if i > 0:
            time.sleep(DELAY_BETWEEN_CALLS)
        signals = await analyze_article(article)
        for sig in signals:
            sig["source_name"] = article.get("source_name")
            sig["article_title"] = article.get("title")
            sig["article_url"] = article.get("url")
        all_signals.extend(signals)
        print(f"[analyzer] {i+1}/{len(batch)} - '{article.get('title', '')[:60]}'")

    print(f"[analyzer] Found {len(all_signals)} signals from {len(batch)} articles")
    return all_signals
