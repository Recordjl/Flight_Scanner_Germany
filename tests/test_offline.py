"""Offline tests with canned API responses. Run: python -m unittest discover tests"""
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from scanner import deals
from scanner.config import load_config
from scanner.dates import cash_slices, todays_slices
from scanner.sources import reddit_rss, seats_aero, serpapi
from scanner.storage import Store

CFG = load_config()

AWARD_ROWS = [
    {"ID": "a1", "Date": "2027-09-14", "Source": "flyingblue",
     "Route": {"OriginAirport": "ORD", "DestinationAirport": "FRA", "Source": "flyingblue"},
     "YAvailable": True, "YMileageCost": "25000", "YRemainingSeats": 4, "YAirlines": "AF",
     "JAvailable": True, "JMileageCost": "65000", "JRemainingSeats": 0, "JAirlines": "AF",
     "JDirect": False},
    {"ID": "a2", "Date": "2027-09-15", "Source": "delta",
     "Route": {"OriginAirport": "CVG", "DestinationAirport": "MUC", "Source": "delta"},
     "YAvailable": True, "YMileageCost": "80000", "YRemainingSeats": 1,
     "JAvailable": False, "JMileageCost": "0"},
    {"ID": "a3", "Date": "2027-09-15", "Source": "emirates",
     "Route": {"OriginAirport": "JFK", "DestinationAirport": "MUC"},
     "YAvailable": True, "YMileageCost": "20000"},
]

GOOGLE = {
    "best_flights": [{"price": 3000, "flights": [
        {"airline": "Delta", "arrival_airport": {"id": "CDG"}},
        {"airline": "Air France", "arrival_airport": {"id": "MUC"}}]}],
    "other_flights": [{"price": 2400, "flights": [
        {"airline": "United", "arrival_airport": {"id": "ORD"}},
        {"airline": "Lufthansa", "arrival_airport": {"id": "MUC"}}]}],
    "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?x"},
}

RSS = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Flying Blue promo to Munich for Oktoberfest</title>
<link href="https://www.reddit.com/r/awardtravel/comments/abc/"/>
<updated>2026-10-05T12:00:00+00:00</updated><content>great deal</content></entry>
<entry><title>Hawaii question</title><link href="https://www.reddit.com/r/awardtravel/comments/def/"/>
<updated>2026-10-05T12:00:00+00:00</updated><content>nothing</content></entry>
</feed>"""


class AwardParsing(unittest.TestCase):
    def test_to_fares(self):
        fares = seats_aero.to_fares(AWARD_ROWS, CFG, "outbound")
        kinds = {(f.program, f.cabin) for f in fares}
        # delta economy has only 1 seat (need 2); emirates is not a configured program
        self.assertEqual(kinds, {("flyingblue", "economy"), ("flyingblue", "business")})
        biz = next(f for f in fares if f.cabin == "business")
        self.assertEqual(biz.price_per_person, 65000)
        self.assertIn("position CVG-ORD", biz.extra["notes"])
        self.assertIn("train from FRA", biz.extra["notes"])
        self.assertIn("seat count unknown", biz.extra["notes"])


class CashParsing(unittest.TestCase):
    def test_scan_prices_per_person_and_mixed(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = GOOGLE
        with mock.patch("scanner.sources.serpapi.requests.get", return_value=resp) as get:
            fares = serpapi.scan("k", CFG, [(date(2027, 9, 14), date(2027, 9, 24))])
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["arrival_id"], "MUC,STR")
        fam = next(f for f in fares if f.extra["search"] == "economy_family")
        self.assertEqual(fam.price_per_person, 800)
        self.assertEqual(fam.destination, "MUC")
        biz = next(f for f in fares if f.extra["search"] == "business_1")
        self.assertEqual(biz.extra["mixed_total"], 4800)

    def test_error_response_skipped(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"error": "Google Flights hasn't returned any results"}
        with mock.patch("scanner.sources.serpapi.requests.get", return_value=resp):
            self.assertEqual(serpapi.scan("k", CFG, [(date(2027, 9, 14), date(2027, 9, 24))]), [])


class Dates(unittest.TestCase):
    def test_horizon_blocks_far_dates(self):
        self.assertEqual(cash_slices(CFG, date(2026, 10, 6)), [])
        self.assertTrue(cash_slices(CFG, date(2027, 1, 1)))

    def test_rotation_covers_everything(self):
        today = date(2027, 1, 1)
        all_slices = set(cash_slices(CFG, today))
        seen = set()
        for i in range(60):
            picked = todays_slices(CFG, date.fromordinal(today.toordinal() + i))
            self.assertLessEqual(len(picked), CFG["cash"]["date_pairs_per_run"])
            seen.update(picked)
        self.assertEqual(seen, all_slices)


class Evaluate(unittest.TestCase):
    def test_threshold_and_new_low(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "h.sqlite")
            fares = seats_aero.to_fares(AWARD_ROWS, CFG, "outbound")
            alerts, _ = deals.evaluate(fares, store, CFG["thresholds"])
            self.assertEqual({f.cabin for f, _ in alerts}, {"economy", "business"})
            store.save("2026-10-06", fares)
            cheaper = seats_aero.to_fares(AWARD_ROWS, CFG, "outbound")
            for f in cheaper:
                f.price_per_person -= 1000
            alerts, _ = deals.evaluate(cheaper, store, CFG["thresholds"])
            self.assertTrue(all("new low" in why for _, why in alerts))
            self.assertTrue(deals.describe(alerts[0][0]))
            store.close()


class Reddit(unittest.TestCase):
    def test_keyword_match(self):
        posts = reddit_rss._parse(RSS, "awardtravel", datetime(2026, 10, 5, tzinfo=timezone.utc),
                                  [(k, __import__("re").compile(rf"\b{k}\b", 2)) for k in ["Munich"]])
        self.assertEqual([p.title for p in posts], ["Flying Blue promo to Munich for Oktoberfest"])


if __name__ == "__main__":
    unittest.main()
