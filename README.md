# Flight Scanner Germany

Daily scan for CVG → Munich/Stuttgart flights around Oktoberfest 2027 (depart Sep 10 – Oct 1).
It looks for 1 business seat plus 2 economy seats (2 adults + a child with their own seat) and also tracks all-economy. Alerts go to your phone through [ntfy](https://ntfy.sh).

| Source | What it finds | Cost |
|---|---|---|
| [seats.aero](https://seats.aero) Partner API | Award seats on the programs your points transfer to, plus Delta | Pro subscription (1,000 calls/day) |
| [SerpAPI](https://serpapi.com) Google Flights | Cash fares, rotating through date pairs | Free tier (250 searches/month) |
| Reddit RSS | Award-travel posts that mention Munich/Germany | Free, best effort |

Award searches also cover US hubs (ORD, EWR, IAD, ATL, DTW, JFK, BOS) and Frankfurt/Zurich, because seats.aero has little data for CVG itself.
Alerts note when a deal needs a separate flight from CVG to the hub, or a train from FRA/ZRH. All settings live in [config.yaml](config.yaml).

## Setup

1. Create an empty **private** repo on github.com, then push:
   ```
   git remote add origin https://github.com/<you>/flight-scanner-germany.git
   git push -u origin main
   ```
2. In the repo, open **Settings → Secrets and variables → Actions** and add:
   - `SEATS_AERO_KEY`: from seats.aero/settings, API tab (starts with `pro_`)
   - `SERPAPI_KEY`: from serpapi.com/manage-api-key
   - `NTFY_TOPIC`: a long random topic name. Anyone who knows it can read your alerts. Generate one with
     `py -c "import secrets;print('cvg-okt-'+secrets.token_urlsafe(16))"`, then subscribe to it in the ntfy phone app.
   - `NTFY_TOKEN`: optional, only needed if you use a paid ntfy account with a reserved topic.
3. Open **Actions → Daily flight scan → Run workflow** to test it. After that it runs every day at about 7 AM Eastern.

## Run locally

```
py -m pip install -r requirements.txt
py -m unittest discover tests
$env:SEATS_AERO_KEY="pro_..."; $env:SERPAPI_KEY="..."; py -m scanner.main --dry-run
```

`--dry-run` prints the notifications instead of sending them. `--no-reddit` skips Reddit.

## Notes

- **Booking windows:** award seats for Sep 2027 open about 330–360 days ahead, from mid-Oct to Nov 2026. Cash searches start automatically once the return dates are within 330 days (`cash.horizon_days`).
- **Mixed cabin:** no API can price 1 business + 2 economy as one booking. Cash prices are the sum of a 1-adult business search and a 1-adult + 1-child economy search. For awards, look for "J+Y same day" and confirm the flights match before booking.
- **Award seat counts:** a seat count of 0 means seats.aero doesn't know how many are left (some programs don't report it). Always confirm 3 seats on the airline's site.
- **Thresholds** are starting guesses. Once you've watched real prices for a few weeks, adjust them in `config.yaml`.
- Price history is saved in `data/history.sqlite`, which the workflow commits back to the repo after each run.
