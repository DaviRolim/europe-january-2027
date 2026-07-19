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

Prices are pulled from Google Flights via the `fast-flights` Python package. The site exposes a Google Flights purchase/search link for each candidate route; Google Flights should be used to confirm the fare and then complete checkout with the airline or agency shown there.

Prices are planning signals only. Always verify directly before buying.
