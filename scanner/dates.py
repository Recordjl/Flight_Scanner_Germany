"""Date-window helpers, including the daily rotation for rate-limited cash searches."""
from datetime import timedelta


def departure_dates(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def return_window(cfg):
    """Earliest and latest possible return dates (for one-way award searches home)."""
    trip = cfg["trip"]
    return (trip["depart_start"] + timedelta(days=trip["min_nights"]),
            trip["depart_end"] + timedelta(days=trip["max_nights"]))


def cash_slices(cfg, today):
    """All bookable (depart, return) pairs the cash scanner cycles through."""
    trip = cfg["trip"]
    horizon = today + timedelta(days=cfg["cash"]["horizon_days"])
    return [
        (d, d + timedelta(days=n))
        for d in departure_dates(trip["depart_start"], trip["depart_end"])
        for n in cfg["cash"]["rotation_nights"]
        if d + timedelta(days=n) <= horizon
    ]


def todays_slices(cfg, today):
    """Pick today's slices deterministically so successive days cover the whole window."""
    slices = cash_slices(cfg, today)
    per_run = cfg["cash"]["date_pairs_per_run"]
    if not slices:
        return []
    # Stride through the list so each day samples spread-out dates, not adjacent ones.
    runs_per_cycle = -(-len(slices) // per_run)
    offset = today.toordinal() % runs_per_cycle
    return [slices[i] for i in range(offset, len(slices), runs_per_cycle)][:per_run]
