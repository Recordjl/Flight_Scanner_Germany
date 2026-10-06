"""Load config.yaml and secrets from environment variables."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Secrets:
    serpapi_key: str
    seats_aero_key: str
    ntfy_topic: str
    ntfy_token: str


def load_config(path=None):
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    trip = cfg["trip"]
    for key in ("depart_start", "depart_end"):
        if not isinstance(trip[key], date):
            trip[key] = date.fromisoformat(str(trip[key]))
    return cfg


def load_secrets():
    env = os.environ.get
    return Secrets(
        serpapi_key=env("SERPAPI_KEY", ""),
        seats_aero_key=env("SEATS_AERO_KEY", ""),
        ntfy_topic=env("NTFY_TOPIC", ""),
        ntfy_token=env("NTFY_TOKEN", ""),
    )
