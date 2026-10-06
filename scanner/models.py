"""Common result shapes shared by all sources."""
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Fare:
    source: str              # serpapi / seats.aero
    kind: str                # "cash" or "award"
    cabin: str               # "economy" or "business"
    origin: str
    destination: str
    depart_date: str         # ISO date
    return_date: Optional[str]  # None for one-way award segments
    seats: int               # seats priced/available
    price_per_person: float  # USD for cash, miles for award
    taxes_per_person: float = 0.0  # USD (awards only)
    program: str = ""        # award program, e.g. flyingblue
    airlines: str = ""
    stops: Optional[int] = None
    link: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        """Identity used for new-low tracking (same route/date/cabin/program)."""
        return "|".join([self.kind, self.source, self.program, self.cabin, str(self.seats),
                         self.origin, self.destination, self.depart_date, self.return_date or ""])

    def to_dict(self):
        return asdict(self)


@dataclass
class Chatter:
    title: str
    url: str
    subreddit: str
    created_utc: float
    matched: list
