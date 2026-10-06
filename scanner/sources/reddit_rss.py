"""Award-travel chatter from Reddit's public RSS feeds.

Reddit stopped self-service API apps in Nov 2025, so this reads RSS slowly and gives up
quietly on 403/429. It must never break the flight scan.
"""
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from ..models import Chatter

log = logging.getLogger(__name__)
ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "script:flight-scanner-germany:v1.0 (personal daily deal digest)"


def scan(cfg, now=None):
    rc = cfg["reddit"]
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=rc["lookback_hours"])
    patterns = [(k, re.compile(rf"\b{re.escape(k)}\b", re.I)) for k in rc["keywords"]]
    posts = []
    for i, sub in enumerate(rc["subreddits"]):
        if i:
            time.sleep(rc["seconds_between_requests"])
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/new/.rss",
                             params={"limit": 100}, headers={"User-Agent": USER_AGENT}, timeout=30)
        except requests.RequestException as e:
            log.info("reddit r/%s unreachable: %s", sub, e)
            continue
        if r.status_code in (403, 429):
            log.info("reddit blocked the request (HTTP %s); skipping the rest", r.status_code)
            break
        if not r.ok:
            log.info("reddit r/%s returned HTTP %s", sub, r.status_code)
            continue
        posts.extend(_parse(r.content, sub, cutoff, patterns))
    return posts


def _parse(xml_bytes, sub, cutoff, patterns):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out = []
    for entry in root.iter(f"{ATOM}entry"):
        title = entry.findtext(f"{ATOM}title") or ""
        body = entry.findtext(f"{ATOM}content") or ""
        updated = entry.findtext(f"{ATOM}updated") or entry.findtext(f"{ATOM}published") or ""
        link = entry.find(f"{ATOM}link")
        try:
            when = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        text = f"{title} {re.sub('<[^>]+>', ' ', body)}"
        matched = [k for k, p in patterns if p.search(text)]
        if matched and link is not None:
            out.append(Chatter(title=title, url=link.get("href", ""), subreddit=sub,
                               created_utc=when.timestamp(), matched=matched))
    return out
