"""Decide which fares are alert-worthy and format them."""


def threshold_for(fare, thresholds):
    if fare.kind == "cash":
        return thresholds[f"{fare.cabin}_cash_per_person_rt"]
    return thresholds[f"{fare.cabin}_award_miles_one_way"]


def evaluate(fares, store, thresholds):
    """Return (alerts, rest) lists of (fare, reason). Call before saving this run's fares."""
    best = {}
    alerts, rest = [], []
    for f in fares:
        reasons = []
        if f.price_per_person <= threshold_for(f, thresholds):
            reasons.append("under threshold")
        if thresholds.get("alert_on_new_low"):
            group = (f.kind, f.cabin)
            if group not in best:
                best[group] = store.best_ever(*group)
            if best[group] is not None and f.price_per_person < best[group]:
                reasons.append(f"new low (was {best[group]:,.0f})")
        (alerts if reasons else rest).append((f, ", ".join(reasons)))
    alerts.sort(key=lambda fr: (fr[0].kind, fr[0].cabin, fr[0].price_per_person))
    return alerts, rest


def describe(f):
    if f.kind == "cash":
        price = f"${f.price_per_person:,.0f}/pp RT ({f.seats} pax ${f.extra.get('total', 0):,.0f})"
        if f.extra.get("mixed_total"):
            price += f", mixed 1J+2Y ${f.extra['mixed_total']:,.0f}"
        dates = f"{f.depart_date} → {f.return_date}"
    else:
        seats = f"{f.seats} seats" if f.seats else "seats ?"
        price = f"{f.price_per_person:,.0f} mi one-way, {seats}"
        dates = f"{f.depart_date} ({f.extra.get('direction')})"
    route = f"{f.origin}-{f.destination}"
    who = f.program or f.airlines
    line = f"{f.cabin.title()} {route} {dates}: {price} [{who}]"
    notes = list(f.extra.get("notes") or [])
    if f.extra.get("flights"):
        notes.insert(0, f.extra["flights"])
    if notes:
        line += " — " + "; ".join(notes)
    return line


def cheapest_by_group(fares):
    """Lowest fare per (kind, cabin, direction) for the daily summary."""
    out = {}
    for f in fares:
        group = (f.kind, f.cabin, f.extra.get("direction", "round trip"))
        if group not in out or f.price_per_person < out[group].price_per_person:
            out[group] = f
    return [out[g] for g in sorted(out)]
