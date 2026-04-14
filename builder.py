import os
import json
import time
import httpx
import anthropic
from bs4 import BeautifulSoup
from database import get_checked_builder_content, save_builder_ideas

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:30]:  # cap at 30 pages
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)[:20000]  # cap at 20k chars
    except Exception as e:
        return f"[PDF extraction error: {e}]"


async def fetch_youtube_title(url: str) -> str:
    """Fetch YouTube video title from the page's og:title meta tag."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestingAgent/1.0)"
        }) as client_http:
            resp = await client_http.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            og_title = soup.find("meta", property="og:title")
            if og_title:
                return og_title.get("content", "YouTube Video")
            title_tag = soup.find("title")
            if title_tag:
                return title_tag.text.replace(" - YouTube", "").strip()
            return "YouTube Video"
    except Exception:
        return "YouTube Video"


async def fetch_youtube_transcript_text(url: str) -> str:
    """
    Best-effort transcript extraction.
    Falls back to description text scraped from the page if captions unavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestingAgent/1.0)"
        }) as client_http:
            resp = await client_http.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            # Try to pull description from meta
            desc = soup.find("meta", {"name": "description"}) or soup.find("meta", property="og:description")
            if desc:
                return desc.get("content", "")[:5000]
            return ""
    except Exception:
        return ""


IDEAS_SYSTEM = """You are an elite investment research analyst. You analyze research documents, investor letters, and video content to extract 1–5 actionable thematic investment ideas suitable for a paper trading portfolio.

For each idea provide exactly 3 stock picks. Focus on ideas that are specific, actionable, and grounded in the content provided. Avoid generic themes.

Always respond in valid JSON only."""


def build_ideas_prompt(sources: list[dict]) -> str:
    combined = ""
    for s in sources:
        combined += f"\n\n--- SOURCE: {s['name']} ---\n{s['content']}"
    combined = combined[:25000]

    return f"""Analyze the following investment research content and extract 1–5 strong thematic investment ideas.

{combined}

---

Respond ONLY with this JSON structure (1–5 ideas, exactly 3 stocks each):
{{
  "ideas": [
    {{
      "title": "Short thematic title (4–6 words, e.g. 'AI Infrastructure Buildout')",
      "thesis": "2–3 sentence explanation of why this theme is compelling and potentially unpriced. Be specific to the content.",
      "stocks": [
        {{"ticker": "TICKER", "name": "Company Name", "reason": "One sentence why this specific stock fits"}},
        {{"ticker": "TICKER", "name": "Company Name", "reason": "One sentence why this specific stock fits"}},
        {{"ticker": "TICKER", "name": "Company Name", "reason": "One sentence why this specific stock fits"}}
      ]
    }}
  ]
}}"""


def generate_ideas() -> list[dict]:
    """
    Run Claude analysis on all checked builder sources.
    Returns list of idea dicts. Saves to DB.
    """
    sources = get_checked_builder_content()
    if not sources:
        return []

    # Filter out empty content
    sources = [s for s in sources if s.get("content") and len(s["content"]) > 50]
    if not sources:
        return []

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=IDEAS_SYSTEM,
            messages=[{"role": "user", "content": build_ideas_prompt(sources)}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        ideas = parsed.get("ideas", [])[:5]  # cap at 5
        save_builder_ideas(ideas)
        return ideas

    except json.JSONDecodeError as e:
        print(f"[builder] JSON parse error: {e}")
        return []
    except anthropic.RateLimitError:
        print("[builder] Rate limited")
        time.sleep(10)
        return []
    except Exception as e:
        print(f"[builder] Error: {e}")
        return []
