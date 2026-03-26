#!/usr/bin/env python3
"""
Weekend reorganizer for Hitachi Theme 5 research journal.
Reads research_journal.md, groups entries by topic, prioritizes within each group,
and rewrites the file in organized form. Sends a Telegram summary.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime

JOURNAL_PATH = os.path.expanduser("~/Documents/EraOfAI/research_journal.md")
BOT_TOKEN_FILE = "/Users/ssurender/.claude/channels/telegram/.env"
TELEGRAM_CHAT_ID = "8105393549"

# Topic taxonomy for Theme 5
TOPICS = {
    "AI Governance & Regulation": [
        "govern", "regulat", "policy", "legislat", "ai act", "compliance",
        "audit", "oversight", "framework", "law", "legal", "eu ai", "executive order",
    ],
    "AI Safety & Alignment": [
        "safety", "align", "misalign", "agi", "superintelligence", "control problem",
        "value alignment", "corrigib", "shutdown", "catastroph", "existential",
    ],
    "Reliability & Robustness": [
        "reliab", "robust", "failure", "incident", "outage", "bug", "error",
        "resilience", "fault", "test", "benchmark", "evaluat",
    ],
    "Explainability & Transparency": [
        "explainab", "interpretab", "transparent", "black box", "xai",
        "decision", "trust", "accountab", "audit trail",
    ],
    "Societal Impact & Human Value": [
        "human value", "societal", "job", "labor", "econom", "inequal",
        "bias", "fair", "discriminat", "access", "digital divide", "sovereignty",
    ],
    "Technical Research": [
        "paper", "research", "model", "training", "llm", "neural", "dataset",
        "architecture", "benchmark", "capability", "scaling",
    ],
}

HEADER = """# Hitachi Theme 5 — AI Safety & Reliability Research Journal
*Nightly digest of AI safety, reliability, governance, and alignment links.*
*Reorganized by topic every weekend — links ranked by relevance within each topic.*

"""


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
        return
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
            print(f"Telegram error: {e}", file=sys.stderr)
        time.sleep(0.3)


def parse_journal(path):
    """Parse journal file into list of entry dicts."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        content = f.read()

    entries = []
    # Match markdown list items with link syntax: - **[title](url)** ...
    pattern = re.compile(
        r"- \*\*\[([^\]]+)\]\(([^)]+)\)\*\*(?:[^\n]*)?\n\s+(.+?)(?=\n- |\n###|\n##|\Z)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        title = m.group(1).strip()
        url = m.group(2).strip()
        summary = re.sub(r"\s+", " ", m.group(3)).strip()
        entries.append({"title": title, "url": url, "summary": summary})

    return entries


def classify(entry):
    """Assign entry to best-matching topic."""
    text = (entry["title"] + " " + entry["summary"]).lower()
    best_topic = "Technical Research"
    best_score = 0
    for topic, keywords in TOPICS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_topic = topic
    return best_topic


def reorganize():
    entries = parse_journal(JOURNAL_PATH)
    if not entries:
        msg = "Weekend reorganizer: journal is empty, nothing to reorganize."
        send_telegram(msg)
        print(msg)
        return

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for e in entries:
        if e["url"] not in seen_urls:
            seen_urls.add(e["url"])
            unique.append(e)

    # Group by topic
    grouped = {t: [] for t in TOPICS}
    for e in unique:
        topic = classify(e)
        grouped[topic].append(e)

    # Build reorganized file
    now = datetime.now().strftime("%Y-%m-%d %a")
    lines = [HEADER]
    lines.append(f"*Last reorganized: {now}*\n")

    total = 0
    topic_counts = {}
    for topic, items in grouped.items():
        if not items:
            continue
        lines.append(f"\n## {topic}\n")
        for e in items:
            lines.append(f"- **[{e['title']}]({e['url']})**")
            if e["summary"]:
                lines.append(f"  {e['summary']}\n")
            else:
                lines.append("")
        topic_counts[topic] = len(items)
        total += len(items)

    with open(JOURNAL_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"Reorganized {total} entries across {len(topic_counts)} topics.")

    # Telegram summary
    summary_lines = [f"Theme 5 Journal Reorganized — {now}"]
    summary_lines.append(f"{total} total entries, organized by topic:\n")
    for topic, count in topic_counts.items():
        if count:
            summary_lines.append(f"  {topic}: {count}")
    summary_lines.append(f"\nFile: ~/Documents/EraOfAI/research_journal.md")
    send_telegram("\n".join(summary_lines))


if __name__ == "__main__":
    reorganize()
