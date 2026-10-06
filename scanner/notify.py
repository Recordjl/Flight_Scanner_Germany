"""Push notifications via ntfy.sh (JSON publish so emoji/umlauts survive)."""
import logging

import requests

log = logging.getLogger(__name__)
MAX_BYTES = 4000  # ntfy turns bodies over 4,096 bytes into attachments


def send(topic, title, message, priority=3, tags=None, click="", token="", dry_run=False):
    body = message.encode("utf-8")
    if len(body) > MAX_BYTES:
        message = body[:MAX_BYTES - 20].decode("utf-8", "ignore") + "\n…(truncated)"
    if dry_run or not topic:
        print(f"\n--- ntfy (priority {priority}) {title} ---\n{message}\n")
        return
    payload = {"topic": topic, "title": title, "message": message, "priority": priority,
               "tags": tags or [], "markdown": True}
    if click:
        payload["click"] = click
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post("https://ntfy.sh/", json=payload, headers=headers, timeout=30)
    if not r.ok:
        log.error("ntfy publish failed: HTTP %s %s", r.status_code, r.text[:200])
