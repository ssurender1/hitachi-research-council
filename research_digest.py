#!/usr/bin/env python3
"""
Nightly Hitachi Theme 5 Research Digest — AI Safety & Reliability.
Scans Reddit + YouTube, extracts relevant links with summaries,
appends to a running journal file, sends Telegram summary.
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
JOURNAL_PATH = os.path.expanduser("~/Documents/EraOfAI/research_journal.md")
BOT_TOKEN_FILE = "/Users/ssurender/.claude/channels/telegram/.env"
TELEGRAM_CHAT_ID = "8105393549"

HACKERNEWS_QUERIES = [
    "AI safety",
    "AI alignment",
    "AI governance",
    "AI reliability",
    "AI regulation",
    "artificial intelligence policy",
]

ARXIV_QUERIES = [
    "AI safety alignment",
    "trustworthy AI reliability",
    "AI governance explainability",
]

YOUTUBE_QUERIES = [
    "AI safety reliability 2026",
    "AI governance regulation policy",
    "AI alignment research",
    "artificial intelligence trustworthy explainability",
]

# Posts/videos must contain at least one of these keywords to be included
RELEVANCE_KEYWORDS = [
    "safety", "reliab", "align", "govern", "regulat", "explainab",
    "trustworth", "oversight", "risk", "policy", "sovereign", "control",
    "interpretab", "accountab", "transparent", "audit", "compliance",
    "human value", "ai act", "agi", "frontier model",
]

HN_POSTS_PER_QUERY = 8
ARXIV_RESULTS_PER_QUERY = 5
YOUTUBE_RESULTS_PER_QUERY = 3
MAX_JOURNAL_ENTRIES = 20  # cap per nightly run


# ── Telegram ──────────────────────────────────────────────────────────────────
def get_bot_token():
    try:
        with open(BOT_TOKEN_FILE) as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def send_telegram(text, chat_id=TELEGRAM_CHAT_ID):
    token = get_bot_token()
    if not token:
        print("No Telegram bot token found", file=sys.stderr)
        return
    # Telegram max 4096 chars per message; split if needed
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    ctx = ssl.create_default_context()
    for chunk in chunks:
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, context=ctx, timeout=10)
        except Exception as e:
            print(f"Telegram send error: {e}", file=sys.stderr)
        time.sleep(0.5)


# ── Relevance filtering ────────────────────────────────────────────────────────
def is_relevant(text, min_matches=1):
    t = text.lower()
    return sum(1 for kw in RELEVANCE_KEYWORDS if kw in t) >= min_matches


def is_relevant_strict(text):
    """Require 2+ keyword matches — used for broad sources like arXiv."""
    return is_relevant(text, min_matches=2)


# ── Text summarization (sentence extractor) ────────────────────────────────────
def excerpt(text, max_chars=350):
    """Return up to max_chars of clean text, ending at a sentence boundary."""
    if not text:
        return ""
    # Collapse whitespace/newlines
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    # Try to end at sentence boundary
    cut = text[:max_chars]
    last_period = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if last_period > max_chars // 2:
        return cut[: last_period + 1]
    return cut.rstrip() + "..."


# ── Hacker News (via Algolia API) ─────────────────────────────────────────────
def fetch_hn_query(query, hours=26, max_results=HN_POSTS_PER_QUERY):
    """Search Hacker News via Algolia API — free, no auth required."""
    cutoff_ts = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())
    params = urllib.parse.urlencode({
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff_ts},points>5",
        "hitsPerPage": max_results,
    })
    url = f"https://hn.algolia.com/api/v1/search?{params}"
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HitachiTheme5Digest/1.0"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"HN query '{query}' error: {e}", file=sys.stderr)
        return []

    results = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        points = hit.get("points", 0)
        combined = title
        if not is_relevant(combined):
            continue
        results.append({
            "source": "Hacker News",
            "title": title,
            "url": story_url,
            "summary": f"HN discussion — {points} points, {hit.get('num_comments', 0)} comments.",
            "score": points,
        })
    return results


def fetch_hn(hours=26):
    entries = []
    seen_urls = set()
    for q in HACKERNEWS_QUERIES:
        for e in fetch_hn_query(q, hours=hours):
            if e["url"] not in seen_urls:
                seen_urls.add(e["url"])
                entries.append(e)
        time.sleep(0.5)
    entries.sort(key=lambda x: x["score"], reverse=True)
    return entries


# ── arXiv ─────────────────────────────────────────────────────────────────────
def fetch_arxiv_query(query, max_results=ARXIV_RESULTS_PER_QUERY):
    """Search arXiv for recent papers — free API, no auth required."""
    import xml.etree.ElementTree as ET
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HitachiTheme5Digest/1.0"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        raw = resp.read()
    except Exception as e:
        print(f"arXiv query '{query}' error: {e}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"arXiv XML parse error: {e}", file=sys.stderr)
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    cutoff = datetime.utcnow() - timedelta(days=3)  # arXiv: last 3 days
    results = []

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:id", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)

        title = re.sub(r"\s+", " ", title_el.text).strip() if title_el is not None and title_el.text else ""
        url_post = link_el.text.strip() if link_el is not None and link_el.text else ""
        abstract = re.sub(r"\s+", " ", summary_el.text).strip() if summary_el is not None and summary_el.text else ""

        pub_str = published_el.text if published_el is not None and published_el.text else ""
        try:
            pub_dt = datetime.strptime(pub_str[:19], "%Y-%m-%dT%H:%M:%S")
            if pub_dt < cutoff:
                continue
        except ValueError:
            pass

        combined = title + " " + abstract
        if not is_relevant_strict(combined):
            continue

        results.append({
            "source": "arXiv",
            "title": title,
            "url": url_post,
            "summary": excerpt(abstract, max_chars=400),
            "score": 100,  # papers always high priority
        })

    return results


def fetch_arxiv():
    entries = []
    seen_urls = set()
    for q in ARXIV_QUERIES:
        for e in fetch_arxiv_query(q):
            if e["url"] not in seen_urls:
                seen_urls.add(e["url"])
                entries.append(e)
        time.sleep(1)
    return entries


# ── YouTube ────────────────────────────────────────────────────────────────────
def fetch_youtube_query(query, max_results=YOUTUBE_RESULTS_PER_QUERY):
    """Search YouTube via yt-dlp and return list of video dicts."""
    cmd = [
        "yt-dlp",
        f"ytsearch{max_results}:{query}",
        "--flat-playlist",
        "--print", "%(title)s|||%(webpage_url)s|||%(description)s",
        "--no-warnings",
        "--quiet",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split("\n")
    except Exception as e:
        print(f"yt-dlp error for '{query}': {e}", file=sys.stderr)
        return []

    videos = []
    for line in lines:
        if "|||" not in line:
            continue
        parts = line.split("|||", 2)
        if len(parts) < 2:
            continue
        title = parts[0].strip()
        url = parts[1].strip()
        desc = parts[2].strip() if len(parts) > 2 else ""
        if not title or not url:
            continue
        combined = title + " " + desc
        if not is_relevant(combined):
            continue
        videos.append({
            "source": "YouTube",
            "title": title,
            "url": url,
            "summary": excerpt(desc) if desc else f"Video: {title}",
        })
    return videos


def fetch_youtube():
    entries = []
    seen_urls = set()
    for q in YOUTUBE_QUERIES:
        for v in fetch_youtube_query(q):
            if v["url"] not in seen_urls:
                seen_urls.add(v["url"])
                entries.append(v)
        time.sleep(2)
    return entries


# ── Journal ────────────────────────────────────────────────────────────────────
def append_to_journal(reddit_entries, youtube_entries, date_label):
    """Append today's findings to the running journal file."""
    lines = []
    lines.append(f"\n---\n")
    lines.append(f"## {date_label}\n")

    if reddit_entries:
        lines.append("\n### Hacker News & arXiv\n")
        for e in reddit_entries[:MAX_JOURNAL_ENTRIES // 2]:
            summ = e["summary"] if e["summary"] else "*(no excerpt)*"
            score_str = f", ↑{e['score']}" if e["score"] and e["source"] == "Hacker News" else ""
            lines.append(f"- **[{e['title']}]({e['url']})** *({e['source']}{score_str})*")
            lines.append(f"  {summ}\n")

    if youtube_entries:
        lines.append("\n### YouTube\n")
        for e in youtube_entries[:MAX_JOURNAL_ENTRIES // 2]:
            summ = e["summary"] if e["summary"] else "*(no description)*"
            lines.append(f"- **[{e['title']}]({e['url']})**")
            lines.append(f"  {summ}\n")

    content = "\n".join(lines)

    # Create file with header if it doesn't exist
    if not os.path.exists(JOURNAL_PATH):
        with open(JOURNAL_PATH, "w") as f:
            f.write("# Hitachi Theme 5 — AI Safety & Reliability Research Journal\n")
            f.write("*Nightly digest of AI safety, reliability, governance, and alignment links.*\n")
            f.write("*Reorganized by topic every weekend.*\n")

    with open(JOURNAL_PATH, "a") as f:
        f.write(content)

    return content


# ── Telegram summary ───────────────────────────────────────────────────────────
def build_telegram_summary(hn_arxiv_entries, youtube_entries, date_label):
    reddit_entries = hn_arxiv_entries
    total = len(reddit_entries) + len(youtube_entries)
    if total == 0:
        return f"Theme 5 Digest ({date_label}): No new relevant links found tonight."

    lines = [f"Theme 5 Digest — {date_label}"]
    lines.append(f"{total} new link(s) added to research_journal.md\n")

    if reddit_entries:
        lines.append("Hacker News + arXiv:")
        for e in reddit_entries[:6]:
            title_short = e["title"][:70] + ("..." if len(e["title"]) > 70 else "")
            lines.append(f"  [{e['source']}] {title_short}")
            lines.append(f"  {e['url']}")

    if youtube_entries:
        lines.append("\nYouTube:")
        for e in youtube_entries[:4]:
            title_short = e["title"][:70] + ("..." if len(e["title"]) > 70 else "")
            lines.append(f"  {title_short}")
            lines.append(f"  {e['url']}")

    lines.append(f"\nFull journal: ~/Documents/EraOfAI/research_journal.md")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    date_label = datetime.now().strftime("%Y-%m-%d %a")

    print(f"[{datetime.now():%H:%M}] Fetching Hacker News...", flush=True)
    hn = fetch_hn(hours=26)
    print(f"  {len(hn)} relevant HN posts found")

    print(f"[{datetime.now():%H:%M}] Fetching arXiv...", flush=True)
    arxiv = fetch_arxiv()
    print(f"  {len(arxiv)} relevant arXiv papers found")

    print(f"[{datetime.now():%H:%M}] Fetching YouTube...", flush=True)
    youtube = fetch_youtube()
    print(f"  {len(youtube)} relevant videos found")

    # Combine HN + arXiv; arXiv first (papers > discussions)
    combined = arxiv + hn

    print(f"[{datetime.now():%H:%M}] Appending to journal...")
    append_to_journal(combined, youtube, date_label)

    summary = build_telegram_summary(combined, youtube, date_label)
    print(f"[{datetime.now():%H:%M}] Sending Telegram...")
    send_telegram(summary)
    print("Done.")


if __name__ == "__main__":
    main()
