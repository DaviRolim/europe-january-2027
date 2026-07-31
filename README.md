# Europe January 2027

Static GitHub Pages trip planner for Davi & Sarah's first Europe trip.

- Dates: January 20–February 2, 2027
- Travelers: 2 adults
- Origin: Recife (REC)
- Candidate arrival hubs: Amsterdam (AMS), Paris (CDG), Brussels (BRU)

## Flight updates

`data/flights.json` is updated by:

1. GitHub Actions daily at 08:30 Recife time.
2. Hermes local cron job, if enabled, using `scripts/update_flights.py`.

Prices are pulled from Google Flights via the `fast-flights` Python package. The site exposes encoded Google Flights `tfs` links for each route so the route, dates, currency, and 2-adult search reopen correctly. Google can still change UI/link handling, so always confirm directly before buying.

The updater ignores suspiciously low total fares below R$5,000 for two REC-Europe round-trip tickets; this prevents scraper misreads like the old R$1.8k entries from polluting history.

Prices are planning signals only. Always verify directly before buying.
