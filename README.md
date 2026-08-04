# Europe January 2027

Static GitHub Pages trip planner for Davi & Sarah's first Europe trip.

- Dates scanned: departures on January 19, 20, and 21, 2027, always returning after 14 nights
- Travelers: 2 adults
- Origin: Recife (REC)
- Candidate arrival hubs: Amsterdam (AMS), Paris (CDG), Brussels (BRU), Lisbon (LIS)

Davi cannot depart before January 19, 2027: the 17th is his son's birthday and the 18th is reserved for resting before the trip.

## Flight updates

`data/flights.json` is updated by:

1. GitHub Actions every 6 hours.
2. Hermes local cron job, if enabled, using `scripts/update_flights.py`.

Prices are pulled from Google Flights via the `fast-flights` Python package. Each run scans a small date grid: REC to AMS, CDG, BRU, and LIS across the three allowed departure dates, for 12 route/date searches total. LIS is included because TAP is the only nonstop Recife-Europe carrier and flies into Lisbon, making it the likeliest cheap gateway.

The site exposes encoded Google Flights `tfs` links for each route/date pair so the route, dates, currency, and 2-adult search reopen correctly. Google can still change UI/link handling, so always confirm directly before buying.

The updater keeps suspiciously low total fares below R$5,000 out of the price history, but still surfaces them in `suspicious_fares` for manual confirmation. Normal alerts fire below R$9,000 total for two adults, and urgent alerts fire below R$8,000.

Telegram alerts are sent by `scripts/notify.py` when `data/flights.json` contains an alert. Configure these repository secrets in GitHub Actions:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Prices are planning signals only. Always verify directly before buying.
