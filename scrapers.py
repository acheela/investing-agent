import httpx
import feedparser
from bs4 import BeautifulSoup
from database import get_active_sources, save_article


async def fetch_substack_articles(limit_per_feed=5):
    """Fetch latest articles from all active Substack sources via RSS."""
    sources = get_active_sources("substack")
    results = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for source in sources:
            try:
                resp = await client.get(source["url"])
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:limit_per_feed]:
                    title = entry.get("title", "Untitled")
                    url = entry.get("link", "")
                    published = entry.get("published", "")
                    # Get text content, strip HTML
                    raw_content = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
                    content = BeautifulSoup(raw_content, "lxml").get_text(separator=" ", strip=True)[:3000]

                    article_id = save_article(source["id"], title, url, content, published)
                    if article_id:
                        results.append({
                            "article_id": article_id,
                            "source_id": source["id"],
                            "source_name": source["name"],
                            "title": title,
                            "url": url,
                            "content": content,
                            "published": published,
                        })
            except Exception as e:
                print(f"[scraper] Substack error for {source['name']}: {e}")

    return results


async def fetch_youtube_transcripts(limit_per_channel=3):
    """
    Fetch recent YouTube video info from channels.
    Note: Full transcripts require yt-dlp or YouTube Data API.
    For now we fetch the channel page and extract recent video titles/descriptions
    as signals of what's being discussed.
    """
    sources = get_active_sources("youtube")
    results = []

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (compatible; InvestingAgent/1.0)"
    }) as client:
        for source in sources:
            try:
                # Fetch RSS feed for YouTube channel (public, no API key needed)
                # YouTube exposes RSS at: https://www.youtube.com/feeds/videos.xml?channel_id=...
                # We'll search for the channel ID from the page
                handle_url = source["url"]
                resp = await client.get(handle_url + "/videos")
                soup = BeautifulSoup(resp.text, "lxml")

                # Try to find channel ID in page meta
                channel_id = None
                for link in soup.find_all("link", rel="alternate"):
                    href = link.get("href", "")
                    if "channel_id=" in href:
                        channel_id = href.split("channel_id=")[-1].split("&")[0]
                        break

                if not channel_id:
                    # Try canonical link
                    canonical = soup.find("link", rel="canonical")
                    if canonical:
                        href = canonical.get("href", "")
                        if "/channel/" in href:
                            channel_id = href.split("/channel/")[-1].split("/")[0]

                if channel_id:
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    rss_resp = await client.get(rss_url)
                    feed = feedparser.parse(rss_resp.text)
                    for entry in feed.entries[:limit_per_channel]:
                        title = entry.get("title", "Untitled")
                        url = entry.get("link", "")
                        published = entry.get("published", "")
                        description = ""
                        if hasattr(entry, "media_group"):
                            description = getattr(entry.media_group, "media_description", "")
                        content = f"[YouTube] {title}\n{description}"[:2000]

                        article_id = save_article(source["id"], title, url, content, published)
                        if article_id:
                            results.append({
                                "article_id": article_id,
                                "source_id": source["id"],
                                "source_name": source["name"],
                                "title": title,
                                "url": url,
                                "content": content,
                                "published": published,
                            })
            except Exception as e:
                print(f"[scraper] YouTube error for {source['name']}: {e}")

    return results


async def fetch_twitter_context(limit_per_account=5):
    """
    X/Twitter doesn't allow scraping easily.
    We use web search to find recent notable posts from tracked accounts.
    Returns stubs - actual X integration requires API keys.
    """
    sources = get_active_sources("twitter")
    results = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (compatible; InvestingAgent/1.0)"
    }) as client:
        for source in sources:
            try:
                # Nitter is a Twitter frontend that's sometimes scrapeable
                handle = source["handle"].lstrip("@")
                nitter_url = f"https://nitter.net/{handle}/rss"
                resp = await client.get(nitter_url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:limit_per_account]:
                        title = entry.get("title", "")
                        url = entry.get("link", "").replace("nitter.net", "twitter.com")
                        published = entry.get("published", "")
                        content = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(separator=" ", strip=True)[:1000]

                        if content and len(content) > 20:
                            article_id = save_article(source["id"], title, url, content, published)
                            if article_id:
                                results.append({
                                    "article_id": article_id,
                                    "source_id": source["id"],
                                    "source_name": source["name"],
                                    "title": title,
                                    "url": url,
                                    "content": content,
                                    "published": published,
                                })
            except Exception as e:
                print(f"[scraper] Twitter error for {source['name']}: {e}")

    return results


async def fetch_all():
    """Run all scrapers and return combined new articles."""
    substack = await fetch_substack_articles()
    youtube = await fetch_youtube_transcripts()
    twitter = await fetch_twitter_context()
    all_articles = substack + youtube + twitter
    print(f"[scraper] Fetched {len(substack)} Substack, {len(youtube)} YouTube, {len(twitter)} Twitter articles")
    return all_articles
