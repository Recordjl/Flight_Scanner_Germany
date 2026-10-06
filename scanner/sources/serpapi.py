"""Cash fares from Google Flights via SerpAPI (engine=google_flights).

Docs: https://serpapi.com/google-flights-api - free tier is 250 searches/month.
"""
import logging

import requests

from ..models import Fare

log = logging.getLogger(__name__)
URL = "https://serpapi.com/search.json"
ECONOMY, BUSINESS = 1, 3

# (label, cabin, travel_class, adults, children). Mixed = business + economy_pair.
SEARCHES = [
    ("business_1", "business", BUSINESS, 1, 0),
    ("economy_pair", "economy", ECONOMY, 1, 1),
    ("economy_family", "economy", ECONOMY, 2, 1),
]


def _search(key, origin, destinations, depart, ret, travel_class, adults, children):
    params = {
        "engine": "google_flights", "api_key": key, "type": 1,
        "departure_id": origin, "arrival_id": ",".join(destinations),
        "outbound_date": depart.isoformat(), "return_date": ret.isoformat(),
        "travel_class": travel_class, "adults": adults, "children": children,
        "currency": "USD", "hl": "en", "gl": "us", "sort_by": 2,
    }
    r = requests.get(URL, params=params, timeout=90)
    data = r.json()
    if "error" in data:
        log.info("serpapi %s->%s %s: %s", origin, params["arrival_id"], depart, data["error"])
        return None
    r.raise_for_status()
    return data


def _cheapest(data):
    options = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    priced = [o for o in options if o.get("price")]
    return min(priced, key=lambda o: o["price"]) if priced else None


def scan(key, cfg, slices):
    origin, dests = cfg["trip"]["origin"], cfg["trip"]["destinations"]
    fares = []
    for depart, ret in slices:
        found = {}
        for label, cabin, travel_class, adults, children in SEARCHES:
            data = _search(key, origin, dests, depart, ret, travel_class, adults, children)
            best = _cheapest(data) if data else None
            if not best:
                continue
            legs = best.get("flights") or []
            seats = adults + children
            fare = Fare(
                source="serpapi", kind="cash", cabin=cabin, origin=origin,
                destination=legs[-1]["arrival_airport"]["id"] if legs else "/".join(dests),
                depart_date=depart.isoformat(), return_date=ret.isoformat(), seats=seats,
                price_per_person=best["price"] / seats,  # Google prices are totals for all pax
                airlines=", ".join(sorted({l.get("airline", "") for l in legs})),
                stops=max(len(legs) - 1, 0),
                link=data.get("search_metadata", {}).get("google_flights_url", ""),
                extra={"search": label, "total": best["price"],
                       "price_level": (data.get("price_insights") or {}).get("price_level")},
            )
            found[label] = fare
            fares.append(fare)
        if "business_1" in found and "economy_pair" in found:
            total = found["business_1"].extra["total"] + found["economy_pair"].extra["total"]
            for f in (found["business_1"], found["economy_pair"]):
                f.extra["mixed_total"] = total
    return fares
