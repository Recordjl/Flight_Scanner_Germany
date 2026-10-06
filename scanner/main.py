"""Daily scan: awards (seats.aero), cash (SerpAPI), Reddit chatter -> ntfy push.

Usage: python -m scanner.main [--dry-run] [--no-reddit]
"""
import argparse
import logging
import os
from datetime import date

from . import deals, notify
from .config import load_config, load_secrets
from .dates import todays_slices
from .sources import reddit_rss, seats_aero, serpapi
from .storage import Store

log = logging.getLogger("scanner")
MAX_ALERT_LINES = 10


def run_url():
    repo, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""


def write_job_summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print notifications instead of sending")
    parser.add_argument("--no-reddit", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg, secrets = load_config(), load_secrets()
    today = date.today()
    store = Store()
    fares, errors, award_client = [], [], None

    if secrets.seats_aero_key:
        try:
            award_client, award_fares = seats_aero.scan(secrets.seats_aero_key, cfg)
            fares += award_fares
        except Exception as e:  # noqa: BLE001 - one failing source must not stop the others
            log.exception("seats.aero scan failed")
            errors.append(f"seats.aero: {e}")
    else:
        log.warning("SEATS_AERO_KEY not set; skipping awards")

    slices = todays_slices(cfg, today)
    if not secrets.serpapi_key:
        log.warning("SERPAPI_KEY not set; skipping cash fares")
    elif not slices:
        log.info("No cash date pairs inside the %d-day booking horizon yet", cfg["cash"]["horizon_days"])
    else:
        try:
            log.info("Cash slices today: %s", [(d.isoformat(), r.isoformat()) for d, r in slices])
            fares += serpapi.scan(secrets.serpapi_key, cfg, slices)
        except Exception as e:  # noqa: BLE001
            log.exception("serpapi scan failed")
            errors.append(f"serpapi: {e}")

    chatter = []
    if not args.no_reddit:
        try:
            chatter = [p for p in reddit_rss.scan(cfg) if store.is_new_post(p.url, today.isoformat())]
        except Exception as e:  # noqa: BLE001
            log.warning("reddit scan failed: %s", e)

    alerts, _ = deals.evaluate(fares, store, cfg["thresholds"])
    if award_client:
        award_alerts = [f for f, _ in alerts if f.kind == "award"]
        seats_aero.enrich(award_client, award_alerts, cfg["awards"]["trip_details_max"])
    store.save(today.isoformat(), fares)
    store.close()

    click = run_url()
    send = dict(topic=secrets.ntfy_topic, token=secrets.ntfy_token, click=click, dry_run=args.dry_run)

    if alerts:
        lines = [f"- {deals.describe(f)} ({why})" for f, why in alerts[:MAX_ALERT_LINES]]
        if len(alerts) > MAX_ALERT_LINES:
            lines.append(f"- …and {len(alerts) - MAX_ALERT_LINES} more (see run summary)")
        notify.send(title=f"✈️ {len(alerts)} flight deal(s) CVG → Germany",
                    message="\n".join(lines), priority=4, tags=["airplane", "moneybag"], **send)

    summary = [f"**{len(fares)} fares scanned** ({sum(f.kind == 'award' for f in fares)} award, "
               f"{sum(f.kind == 'cash' for f in fares)} cash), {len(alerts)} alert(s)."]
    summary += [f"- {deals.describe(f)}" for f in deals.cheapest_by_group(fares)]
    if chatter:
        summary.append("\n**Reddit:**")
        summary += [f"- [{p.title}]({p.url}) (r/{p.subreddit}: {', '.join(p.matched)})" for p in chatter[:5]]
    if errors:
        summary.append("\n**Errors:** " + "; ".join(errors))
    notify.send(title="Daily flight scan: CVG → MUC/STR", message="\n".join(summary),
                priority=2, tags=["calendar"], **send)

    write_job_summary(["# Flight scan " + today.isoformat(), *summary, "", "## All alerts",
                       *[f"- {deals.describe(f)} ({why})" for f, why in alerts]])
    return 1 if errors and not fares else 0


if __name__ == "__main__":
    raise SystemExit(main())
