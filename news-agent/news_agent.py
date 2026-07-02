#!/usr/bin/env python3
"""
Market News Agent
Crypto + Indian markets + US AI stocks  ->  Telegram

Required environment variables:
  TELEGRAM_TOKEN      from @BotFather
  TELEGRAM_CHAT_ID    your chat id (see README)
Optional:
  ANTHROPIC_API_KEY   enables the AI filter + one-line summaries

Run:  python news_agent.py
"""

import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

import feedparser
import requests

# ------------------------------------------------------------------ config

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SEEN_FILE = Path("seen.json")   # memory of already-sent stories
MAX_PER_CATEGORY = 4            # max headlines per category per run
SEEN_LIMIT = 800                # how many old story ids to remember

FEEDS = {
    "\u20bf Crypto": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
    ],
    "\U0001f1ee\U0001f1f3 India": [
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://www.livemint.com/rss/markets",
    ],
    "\U0001f916 US AI": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.cnbc.com/id/19854910/device/rss/rss.html",
    ],
}

# US AI category: a headline is kept ONLY if it mentions one of these.
AI_WHITELIST = [
    "nvidia", "nvda", "amd", "advanced micro", "microsoft", "msft",
    "google", "alphabet", "googl", "meta", "palantir", "pltr",
    "broadcom", "avgo", "tsmc", "taiwan semiconductor", "super micro",
    "smci", "openai", "anthropic", "arm holdings", "micron", "oracle",
    "intel", "qualcomm", "semiconductor", "ai chip", "chipmaker",
    "data center", "datacenter", "gpu",
]

# Dropped in every category (noise).
BLOCKLIST = [
    "horoscope", "astrolog", "bollywood", "ipl", "cricket",
    "sponsored", "advertorial", "webinar", "quiz",
]

TAG_RE = re.compile(r"<[^>]+>")

# ------------------------------------------------------------------ memory


def load_seen() -> list[str]:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_seen(seen: list[str]) -> None:
    SEEN_FILE.write_text(json.dumps(seen[-SEEN_LIMIT:]))


# ------------------------------------------------------------------ fetch


def item_id(entry) -> str:
    raw = entry.get("link") or entry.get("id") or entry.get("title", "")
    return hashlib.sha1(raw.encode()).hexdigest()


def fetch_category(urls: list[str]) -> list[dict]:
    items = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            entries = feed.entries[:15]
        except Exception as exc:  # dead feed -> skip, don't crash
            print(f"[warn] could not read {url}: {exc}")
            continue
        for entry in entries:
            summary = TAG_RE.sub("", entry.get("summary", "") or "")
            items.append({
                "id": item_id(entry),
                "title": (entry.get("title") or "").strip(),
                "link": entry.get("link", ""),
                "summary": summary.strip()[:300],
            })
    return items


# ------------------------------------------------------------------ filters


def passes_filters(category: str, item: dict) -> bool:
    text = f"{item['title']} {item['summary']}".lower()
    if any(bad in text for bad in BLOCKLIST):
        return False
    if "US AI" in category:  # strict: AI/semiconductor stock news only
        return any(word in text for word in AI_WHITELIST)
    return True


def claude_rank(category: str, items: list[dict]) -> list[dict]:
    """Optional AI layer: keep only market-moving items, write short
    summaries. Falls back to plain keyword results if no key / on error."""
    if not ANTHROPIC_API_KEY or not items:
        return items[:MAX_PER_CATEGORY]

    numbered = "\n".join(
        f"{i}. {it['title']} :: {it['summary'][:150]}"
        for i, it in enumerate(items)
    )
    prompt = (
        "You are a strict financial news filter for a personal alert bot.\n"
        f"Category: {category}\n"
        "Rules:\n"
        "- Keep only genuinely market-relevant news: price moves, earnings,"
        " deals, regulation, big product launches.\n"
        "- Drop opinion pieces, listicles, promos, and near-duplicates.\n"
        "- If the category is US AI: keep ONLY news about AI/semiconductor"
        " companies or AI-related stocks. Drop everything else.\n"
        f"- Keep at most {MAX_PER_CATEGORY} items.\n\n"
        f"Headlines:\n{numbered}\n\n"
        "Respond with ONLY this JSON, no markdown fences:\n"
        '{"keep": [{"index": 0, "summary": "one line, max 15 words"}]}'
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json()["content"])
        text = text.replace("```json", "").replace("```", "").strip()
        keep = json.loads(text)["keep"]
        chosen = []
        for k in keep[:MAX_PER_CATEGORY]:
            it = dict(items[int(k["index"])])
            it["summary"] = k.get("summary", "")
            chosen.append(it)
        return chosen
    except Exception as exc:
        print(f"[warn] Claude filter failed ({exc}); using keyword results.")
        return items[:MAX_PER_CATEGORY]


# ------------------------------------------------------------------ send


def send_telegram(text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()


# ------------------------------------------------------------------ main


def main() -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID first (see README).")

    seen = load_seen()
    seen_set = set(seen)
    sections = []
    sent_count = 0

    for category, urls in FEEDS.items():
        fresh = [it for it in fetch_category(urls) if it["id"] not in seen_set]

        # Never process the same story twice, even if rejected below.
        for it in fresh:
            seen_set.add(it["id"])
            seen.append(it["id"])

        candidates = [it for it in fresh if passes_filters(category, it)]

        # Drop near-duplicate titles within this run.
        unique, seen_titles = [], set()
        for it in candidates:
            key = it["title"].lower()[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(it)

        chosen = claude_rank(category, unique)
        if not chosen:
            continue

        lines = [f"<b>{category}</b>"]
        for it in chosen:
            title = html.escape(it["title"])
            line = f'\u2022 <a href="{it["link"]}">{title}</a>'
            if ANTHROPIC_API_KEY and it.get("summary"):
                line += f"\n   <i>{html.escape(it['summary'])}</i>"
            lines.append(line)
            sent_count += 1
        sections.append("\n".join(lines))

    if sections:
        send_telegram("\U0001f4ca <b>Market brief</b>\n\n" + "\n\n".join(sections))
        print(f"Sent {sent_count} stories.")
    else:
        print("Nothing new this run.")

    save_seen(seen)


if __name__ == "__main__":
    main()
