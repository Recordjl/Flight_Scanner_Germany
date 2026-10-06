"""Award availability from the seats.aero Partner API (Pro key, cached search only).

Docs: https://developers.seats.aero  - 1,000 calls/day on Pro.
"""
import logging
import time

import requests

from ..dates import return_window
from ..models import Fare

log = logging.getLogger(__name__)
BASE = "https://seats.aero/partnerapi"
CABINS = {"economy": "Y", "business": "J"}
MAX_PAGES = 10


class SeatsAero:
    def __init__(self, key):
        self.session = requests.Session()
        self.session.headers.update({"Partner-Authorization": key, "Accept": "application/json"})

    def _get(self, path, params=None):
        for attempt in range(3):
            r = self.session.get(f"{BASE}{path}", params=params, timeout=60)
            if r.status_code == 429:
                log.warning("seats.aero rate limited (%s); backing off", r.text.strip())
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json() if r.content else {}
        raise RuntimeError("seats.aero: rate limit not cleared after retries")

    def search(self, origins, destinations, start, end, awards_cfg):
        """Cached search, all pages, deduped by availability ID."""
        params = {
            "origin_airport": ",".join(origins),
            "destination_airport": ",".join(destinations),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "cabins": ",".join(CABINS),
            "take": 1000,
            "include_filtered": str(awards_cfg["include_filtered"]).lower(),
            "min_cabin_pct": awards_cfg["min_cabin_pct"],
        }
        rows, seen = [], set()
        for page in range(MAX_PAGES):
            data = self._get("/search", params)
            for row in data.get("data") or []:
                if row.get("ID") not in seen:
                    seen.add(row.get("ID"))
                    rows.append(row)
            if not data.get("hasMore"):
                break
            params["cursor"] = data.get("cursor")
            params["skip"] = len(rows)
        else:
            log.warning("seats.aero: stopped after %d pages; results truncated", MAX_PAGES)
        return rows

    def trip_details(self, availability_id):
        data = self._get(f"/trips/{availability_id}")
        trips = data.get("data") or []
        link = next((b["link"] for b in data.get("booking_links") or [] if b.get("primary")), "")
        return trips, link


def _miles(row, prefix):
    """Mileage cost for a cabin, or None if unavailable. Costs are strings in /search."""
    for field in (f"{prefix}MileageCost", f"{prefix}MileageCostRaw"):
        try:
            value = int(row.get(field) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return None


def _available(row, prefix):
    return bool(row.get(f"{prefix}Available") or row.get(f"{prefix}AvailableRaw"))


def to_fares(rows, cfg, direction):
    awards = cfg["awards"]
    programs = set(awards["programs"])
    home = cfg["trip"]["origin"]
    targets = set(cfg["trip"]["destinations"])
    skipped = set()
    fares = []
    for row in rows:
        source = row.get("Source") or (row.get("Route") or {}).get("Source", "")
        if source not in programs:
            skipped.add(source)
            continue
        route = row.get("Route") or {}
        origin, dest = route.get("OriginAirport", ""), route.get("DestinationAirport", "")
        us_end, eu_end = (origin, dest) if direction == "outbound" else (dest, origin)
        ready = {c: _available(row, p) and _miles(row, p) for c, p in CABINS.items()}
        for cabin, prefix in CABINS.items():
            if not ready[cabin]:
                continue
            remaining = int(row.get(f"{prefix}RemainingSeats") or 0)  # 0 = unknown
            if cabin == "economy" and 0 < remaining < 2:
                continue  # economy always needs at least 2 seats
            notes = []
            if us_end != home:
                notes.append(f"position {home}-{us_end}")
            if eu_end not in targets:
                notes.append(f"train from {eu_end}")
            if remaining == 0:
                notes.append("seat count unknown")
            if ready["economy"] and ready["business"]:
                notes.append("J+Y same day")
            fares.append(Fare(
                source="seats.aero", kind="award", cabin=cabin, origin=origin, destination=dest,
                depart_date=row.get("Date", ""), return_date=None, seats=remaining,
                price_per_person=float(_miles(row, prefix)), program=source,
                airlines=row.get(f"{prefix}Airlines") or "",
                stops=0 if row.get(f"{prefix}Direct") else None,
                extra={"availability_id": row.get("ID"), "direction": direction,
                       "notes": notes, "updated_at": row.get("UpdatedAt")},
            ))
    if skipped:
        log.info("seats.aero: ignored programs not in config: %s", ", ".join(sorted(skipped)))
    return fares


def scan(key, cfg):
    client = SeatsAero(key)
    awards, trip = cfg["awards"], cfg["trip"]
    ret_start, ret_end = return_window(cfg)
    outbound = client.search(awards["us_airports"], awards["europe_airports"],
                             trip["depart_start"], trip["depart_end"], awards)
    inbound = client.search(awards["europe_airports"], awards["us_airports"],
                            ret_start, ret_end, awards)
    log.info("seats.aero: %d outbound, %d return availability rows", len(outbound), len(inbound))
    return client, to_fares(outbound, cfg, "outbound") + to_fares(inbound, cfg, "return")


def enrich(client, fares, limit):
    """Add flight numbers and booking links to the top alert candidates."""
    for fare in fares[:limit]:
        try:
            trips, link = client.trip_details(fare.extra["availability_id"])
        except Exception as e:  # noqa: BLE001 - enrichment is best effort
            log.warning("seats.aero trip lookup failed: %s", e)
            continue
        cabin_trips = [t for t in trips if t.get("Cabin") == fare.cabin]
        if cabin_trips:
            best = min(cabin_trips, key=lambda t: t.get("MileageCost") or 10**9)
            fare.extra["flights"] = best.get("FlightNumbers", "")
            fare.extra["departs_at"] = best.get("DepartsAt", "")
            fare.stops = best.get("Stops", fare.stops)
        fare.link = link
