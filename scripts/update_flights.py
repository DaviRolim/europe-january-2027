#!/usr/bin/env python3
"""Update REC -> Europe Jan 2027 flight prices for the trip site.

Best-effort Google Flights lookup via fast-flights. Some route/date pairs may
fail when Google anti-bot checks trigger; failures are recorded in
data/flights.json instead of crashing the whole update.
"""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

ROUTES = {
    "AMS": {"city": "Amsterdã", "country": "Holanda", "label": "Aeroporto de Amsterdã Schiphol"},
    "CDG": {"city": "Paris", "country": "França", "label": "Aeroporto Paris Charles de Gaulle"},
    "BRU": {"city": "Bruxelas", "country": "Bélgica", "label": "Aeroporto de Bruxelas"},
    # TAP is the only nonstop Recife<->Europe carrier and flies into LIS, so LIS is the likeliest cheap gateway.
    "LIS": {"city": "Lisboa", "country": "Portugal", "label": "Aeroporto de Lisboa Humberto Delgado"},
}
ORIGIN = "REC"
MIN_DEPART_DATE = "2027-01-19"
DEPART_DATES: list[str] = ["2027-01-19", "2027-01-20", "2027-01-21"]
RETURN_NIGHTS = 14
OLD_DEPART_DATE = "2027-01-20"
ADULTS = 2
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "flights.json"
SOURCE_NAME = "Google Flights"
SOURCE_URL = "https://www.google.com/travel/flights"
MIN_REASONABLE_TOTAL_BRL = 5_000
MAX_REASONABLE_TOTAL_BRL = 80_000
MAX_QUERIES_PER_RUN = 12
QUERY_DELAY_SECONDS = (2.5, 6.0)
ALERT_BELOW_BRL = 9_000
URGENT_BELOW_BRL = 8_000


def travel_date_pairs() -> Iterable[tuple[str, str]]:
    min_depart = date.fromisoformat(MIN_DEPART_DATE)
    for depart in DEPART_DATES:
        depart_day = date.fromisoformat(depart)
        if depart_day < min_depart:
            raise ValueError(f"Data de ida antes de {MIN_DEPART_DATE}: {depart}")
        return_day = depart_day + timedelta(days=RETURN_NIGHTS)
        yield depart, return_day.isoformat()


def return_date_for_depart(depart_date: str) -> str:
    return (date.fromisoformat(depart_date) + timedelta(days=RETURN_NIGHTS)).isoformat()


def google_flights_url(dest: str, depart_date: str, return_date: str) -> str:
    """Create a Google Flights URL with route/date/traveler state encoded.

    Plain `?q=voos REC...` links are often ignored by Google Flights and open a
    blank search. The `tfs` parameter is what Google Flights/fast-flights uses
    internally, so it is much more reliable for reopening the exact search.
    """
    try:
        from fast_flights import FlightData, Passengers, create_filter

        tfs = create_filter(
            flight_data=[
                FlightData(date=depart_date, from_airport=ORIGIN, to_airport=dest),
                FlightData(date=return_date, from_airport=dest, to_airport=ORIGIN),
            ],
            trip="round-trip",
            passengers=Passengers(adults=ADULTS, children=0, infants_in_seat=0, infants_on_lap=0),
            seat="economy",
        ).as_b64().decode("utf-8")
        return f"{SOURCE_URL}?tfs={tfs}&hl=pt-BR&curr=BRL&tfu=EgQIABABIgA"
    except Exception:
        query = quote_plus(
            f"voos REC para {dest} ida {depart_date} volta {return_date} 2 adultos"
        )
        return f"https://www.google.com/search?q={query}"


def booking_links(dest: str, depart_date: str, return_date: str) -> dict[str, str]:
    """Best-effort public links for re-running the same search and buying."""
    return {
        "google_flights": google_flights_url(dest, depart_date, return_date),
        "skyscanner": f"https://www.skyscanner.com.br/transport/flights/rec/{dest.lower()}/{depart_date.replace('-', '')}/{return_date.replace('-', '')}/?adults=2",
        "kayak": f"https://www.kayak.com.br/flights/REC-{dest}/{depart_date}/{return_date}/2adults",
    }


def is_suspicious_low_fare(price_brl: int | None) -> bool:
    return bool(price_brl and 0 < price_brl < MIN_REASONABLE_TOTAL_BRL)


def is_reasonable_total_fare(price_brl: int | None) -> bool:
    """Guard against scraper misreads like R$1.805 for two REC-Europe tickets."""
    return bool(price_brl and MIN_REASONABLE_TOTAL_BRL <= price_brl <= MAX_REASONABLE_TOTAL_BRL)


def parse_brl(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def format_brl(value: int | None) -> str:
    if value is None:
        return "R$—"
    return f"R${value:,}".replace(",", ".")


def day_key(iso: str) -> str:
    return iso[:10]


def make_suspicious_entry(route: dict[str, Any], flight: dict[str, Any]) -> dict[str, Any]:
    links = route.get("booking_links") or {}
    return {
        "origin": route.get("origin", ORIGIN),
        "destination": route.get("destination"),
        "destination_label": route.get("label"),
        "depart_date": route.get("depart_date"),
        "return_date": route.get("return_date"),
        "price_brl": flight.get("price_brl"),
        "airline": flight.get("name"),
        "stops": flight.get("stops"),
        "url": links.get("google_flights") or SOURCE_URL,
    }


def make_history_entry(payload: dict[str, Any], route: dict[str, Any], captured_at: str) -> dict[str, Any]:
    cheapest = route.get("cheapest") or {}
    links = route.get("booking_links") or {}
    return {
        "date": day_key(captured_at),
        "captured_at": captured_at,
        "origin": payload.get("origin", ORIGIN),
        "destination": route.get("destination"),
        "destination_label": route.get("label"),
        "depart_date": route.get("depart_date"),
        "return_date": route.get("return_date"),
        "travelers": payload.get("travelers", ADULTS),
        "price_brl": cheapest.get("price_brl"),
        "airline": cheapest.get("name"),
        "duration": cheapest.get("duration"),
        "stops": cheapest.get("stops"),
        "departure": cheapest.get("departure"),
        "price_level": route.get("price_level"),
        "source_name": route.get("source_name", SOURCE_NAME),
        "search_url": links.get("google_flights") or payload.get("source_url") or SOURCE_URL,
        "booking_links": links,
    }


def history_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    depart_date = entry.get("depart_date") or OLD_DEPART_DATE
    return (entry.get("date") or "", entry.get("destination") or "", depart_date)


def history_sort_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        entry.get("date") or "",
        entry.get("captured_at") or "",
        entry.get("destination") or "",
        entry.get("depart_date") or OLD_DEPART_DATE,
    )


def bootstrap_history(previous: dict[str, Any]) -> list[dict[str, Any]]:
    history = previous.get("price_history") if isinstance(previous, dict) else None
    if isinstance(history, list):
        valid_history = []
        for h in history:
            if not isinstance(h, dict) or not h.get("date") or not is_reasonable_total_fare(h.get("price_brl")):
                continue
            entry = h.copy()
            dest = entry.get("destination")
            if not dest and previous.get("best_destination"):
                dest = previous["best_destination"]
                entry["destination"] = dest
            entry["depart_date"] = entry.get("depart_date") or OLD_DEPART_DATE
            entry["return_date"] = entry.get("return_date") or return_date_for_depart(entry["depart_date"])
            if dest in ROUTES:
                links = booking_links(dest, entry["depart_date"], entry["return_date"])
                entry["booking_links"] = links
                entry["search_url"] = links["google_flights"]
                entry["destination_label"] = entry.get("destination_label") or ROUTES[dest]["label"]
            valid_history.append(entry)
        return merge_history_entries(valid_history)

    # First deployment after adding history: seed one point from the last known valid fare.
    if not isinstance(previous, dict) or not is_reasonable_total_fare(previous.get("best_price_brl")):
        return []
    dest = previous.get("best_destination")
    route = next((r for r in previous.get("routes", []) if r.get("destination") == dest), None)
    if not route:
        return []
    route["depart_date"] = route.get("depart_date") or OLD_DEPART_DATE
    route["return_date"] = route.get("return_date") or return_date_for_depart(route["depart_date"])
    return [make_history_entry(previous, route, previous.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"))]


def merge_history_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in entries:
        price = entry.get("price_brl")
        if not is_reasonable_total_fare(price):
            continue
        key = history_identity(entry)
        existing = by_key.get(key)
        if (not existing) or price < existing.get("price_brl", 10**12):
            by_key[key] = entry
        elif price == existing.get("price_brl"):
            # Keep the daily low, but refresh metadata/link if the same fare is still visible.
            existing.update({k: v for k, v in entry.items() if v is not None})
            by_key[key] = existing
    return sorted(by_key.values(), key=history_sort_key)


def merge_history(previous: dict[str, Any], payload: dict[str, Any], captured_at: str) -> list[dict[str, Any]]:
    entries = bootstrap_history(previous)
    for route in payload.get("routes", []):
        cheapest = route.get("cheapest") or {}
        if is_reasonable_total_fare(cheapest.get("price_brl")):
            entries.append(make_history_entry(payload, route, captured_at))
    return merge_history_entries(entries)


def summarize_history_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [h for h in entries if h.get("price_brl")]
    if not valid:
        return {}
    valid = sorted(valid, key=history_sort_key)
    dates = sorted({h["date"] for h in valid if h.get("date")})
    latest_date = dates[-1]
    latest_entries = [h for h in valid if h.get("date") == latest_date]
    latest = min(latest_entries, key=lambda h: h["price_brl"])
    previous = None
    if len(dates) > 1:
        previous_date = dates[-2]
        previous_entries = [h for h in valid if h.get("date") == previous_date]
        previous = min(previous_entries, key=lambda h: h["price_brl"])
    lowest = min(valid, key=lambda h: h["price_brl"])
    highest = max(valid, key=lambda h: h["price_brl"])
    prices = [h["price_brl"] for h in valid]
    avg = round(sum(prices) / len(prices))
    delta_prev = latest["price_brl"] - previous["price_brl"] if previous else None
    delta_low = latest["price_brl"] - lowest["price_brl"]
    return {
        "days_tracked": len(dates),
        "latest": latest,
        "previous": previous,
        "lowest": lowest,
        "highest": highest,
        "average_price_brl": avg,
        "delta_vs_previous_brl": delta_prev,
        "delta_vs_lowest_brl": delta_low,
    }


def history_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_history_entries(history)
    if not summary:
        return {}
    by_route = {}
    destinations = sorted({h.get("destination") for h in history if h.get("destination")})
    for dest in destinations:
        route_summary = summarize_history_entries([h for h in history if h.get("destination") == dest])
        if route_summary:
            by_route[dest] = route_summary
    summary["by_route"] = by_route
    return summary


def flight_to_dict(f: Any) -> dict[str, Any]:
    # fast-flights exposes dataclass-like objects.
    try:
        d = asdict(f)
    except TypeError:
        d = {k: getattr(f, k, None) for k in [
            "is_best", "name", "departure", "arrival", "arrival_time_ahead",
            "duration", "stops", "delay", "price"
        ]}
    d["price_brl"] = parse_brl(d.get("price"))
    return d


def query_route(dest: str, depart_date: str, return_date: str) -> dict[str, Any]:
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter

    meta = ROUTES[dest]
    base = {
        "origin": ORIGIN,
        "destination": dest,
        **meta,
        "depart_date": depart_date,
        "return_date": return_date,
        "adults": ADULTS,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "booking_links": booking_links(dest, depart_date, return_date),
        "status": "ok",
    }

    try:
        filter_data = create_filter(
            flight_data=[
                FlightData(date=depart_date, from_airport=ORIGIN, to_airport=dest),
                FlightData(date=return_date, from_airport=dest, to_airport=ORIGIN),
            ],
            trip="round-trip",
            passengers=Passengers(adults=ADULTS, children=0, infants_in_seat=0, infants_on_lap=0),
            seat="economy",
        )
        result = get_flights_from_filter(filter_data, currency="BRL", mode="fallback")
        flights = [flight_to_dict(f) for f in getattr(result, "flights", [])]
        valid_flights = []
        suspicious_flights = []
        for f in flights:
            if is_reasonable_total_fare(f.get("price_brl")):
                valid_flights.append(f)
            elif is_suspicious_low_fare(f.get("price_brl")):
                suspicious_flights.append(f)
        # De-dupe by airline/departure/arrival/price.
        seen = set()
        unique = []
        for f in valid_flights:
            key = (f.get("name"), f.get("departure"), f.get("arrival"), f.get("price"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)
        unique.sort(key=lambda f: f.get("price_brl") or 10**12)
        cheapest = unique[0] if unique else None
        route = {
            **base,
            "status": "ok" if cheapest else "ignored",
            "price_level": getattr(result, "current_price", None),
            "cheapest": cheapest,
            "flights": unique[:8],
            "suspicious_prices_ignored": len(suspicious_flights),
            "suspicious_fares": [],
            "error": None if cheapest else (
                f"Consulta retornou apenas preços suspeitos abaixo de {format_brl(MIN_REASONABLE_TOTAL_BRL)} para 2 pessoas; confira manualmente antes de comprar."
                if suspicious_flights else None
            ),
        }
        route["suspicious_fares"] = [make_suspicious_entry(route, f) for f in suspicious_flights]
        return route
    except Exception as e:  # keep other routes updating
        raw = str(e)
        if "turnstile" in raw.lower() or "no token provided" in raw.lower() or "401" in raw:
            error = "Temporariamente indisponível — nova tentativa automática em breve."
        else:
            error = f"{type(e).__name__}: {raw[:180].replace(chr(10), ' ')}"
        return {
            **base,
            "status": "error",
            "price_level": None,
            "cheapest": None,
            "flights": [],
            "suspicious_prices_ignored": 0,
            "suspicious_fares": [],
            "error": error,
        }


def collect_suspicious_fares(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suspicious = []
    for route in routes:
        suspicious.extend(route.get("suspicious_fares") or [])
    return sorted(suspicious, key=lambda item: item.get("price_brl") or 10**12)


def alert_from_route(best: dict[str, Any] | None, suspicious_fares: list[dict[str, Any]]) -> dict[str, Any]:
    if best and best.get("cheapest"):
        cheapest = best["cheapest"]
        price = cheapest.get("price_brl")
        level = None
        if price and price < URGENT_BELOW_BRL:
            level = "urgent"
        elif price and price < ALERT_BELOW_BRL:
            level = "alert"
        if level:
            url = (best.get("booking_links") or {}).get("google_flights") or SOURCE_URL
            level_message = (
                "Tarifa urgente encontrada"
                if level == "urgent" else f"Tarifa abaixo de {format_brl(ALERT_BELOW_BRL)} encontrada"
            )
            message = (
                f"{level_message}: {format_brl(price)} para REC → {best.get('destination')} "
                f"({best.get('depart_date')} → {best.get('return_date')})."
            )
            return {
                "level": level,
                "price_brl": price,
                "destination": best.get("destination"),
                "depart_date": best.get("depart_date"),
                "return_date": best.get("return_date"),
                "airline": cheapest.get("name"),
                "stops": cheapest.get("stops"),
                "url": url,
                "message": message,
            }

    if suspicious_fares:
        fare = suspicious_fares[0]
        return {
            "level": "suspicious",
            "price_brl": fare.get("price_brl"),
            "destination": fare.get("destination"),
            "depart_date": fare.get("depart_date"),
            "return_date": fare.get("return_date"),
            "airline": fare.get("airline"),
            "stops": fare.get("stops"),
            "url": fare.get("url") or SOURCE_URL,
            "message": (
                f"Preço suspeito encontrado: {format_brl(fare.get('price_brl'))} para REC → {fare.get('destination')}. "
                "Esse valor pode ser erro do scraper e precisa de confirmação manual antes da compra."
            ),
        }

    return {
        "level": "none",
        "price_brl": None,
        "destination": None,
        "depart_date": None,
        "return_date": None,
        "airline": None,
        "stops": None,
        "url": None,
        "message": "Nenhuma tarifa abaixo do limite de alerta foi encontrada.",
    }


def route_date_queries() -> Iterable[tuple[str, str, str]]:
    for dest in ROUTES:
        for depart_date, return_date in travel_date_pairs():
            yield dest, depart_date, return_date


def run_queries() -> tuple[list[dict[str, Any]], bool]:
    routes = []
    stopped_for_budget = False
    for index, (dest, depart_date, return_date) in enumerate(route_date_queries()):
        if index >= MAX_QUERIES_PER_RUN:
            stopped_for_budget = True
            break
        if index > 0:
            time.sleep(random.uniform(*QUERY_DELAY_SECONDS))
        routes.append(query_route(dest, depart_date, return_date))
    return routes, stopped_for_budget


def main() -> int:
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text())
        except Exception:
            previous = {}

    routes, stopped_for_budget = run_queries()
    ok_routes = [r for r in routes if (r.get("cheapest") or {}).get("price_brl")]
    suspicious_fares = collect_suspicious_fares(routes)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not ok_routes and isinstance(previous, dict) and previous.get("best_price_brl"):
        # Avoid replacing useful fare data with an all-failed anti-bot run.
        previous["last_attempt_at"] = now
        previous["last_attempt_note"] = "A última consulta automática não capturou tarifas válidas; mantendo o último preço válido."
        previous["last_attempt_routes"] = routes
        previous["suspicious_fares"] = suspicious_fares
        previous["alert"] = alert_from_route(None, suspicious_fares)
        OUT.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + "\n")
        print(
            f"Nenhuma tarifa válida capturada hoje; mantive o último melhor preço: {format_brl(previous['best_price_brl'])} "
            f"para {previous.get('best_destination_label')} ({previous.get('best_destination')})."
        )
        if suspicious_fares:
            print(f"Há {len(suspicious_fares)} tarifa(s) suspeita(s) para conferência manual.")
        print(f"Updated {OUT}")
        return 0

    best = min(ok_routes, key=lambda r: (r["cheapest"] or {})["price_brl"]) if ok_routes else None
    date_pairs = [{"depart_date": depart, "return_date": ret} for depart, ret in travel_date_pairs()]

    payload = {
        "updated_at": now,
        "origin": ORIGIN,
        "origin_label": "Recife / Guararapes–Gilberto Freyre International Airport",
        "depart_dates": DEPART_DATES,
        "return_nights": RETURN_NIGHTS,
        "date_pairs": date_pairs,
        "depart_date": best["depart_date"] if best else date_pairs[0]["depart_date"],
        "return_date": best["return_date"] if best else date_pairs[0]["return_date"],
        "travelers": ADULTS,
        "currency": "BRL",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_note": "Preços capturados via Google Flights usando fast-flights, em modo melhor esforço. O monitor busca REC → Europa para 2 adultos em 3 datas de ida a partir de 19/01/2027, sempre com 14 noites. Leituras abaixo de R$5.000 ficam fora do histórico porque podem ser erro do scraper, mas aparecem como tarifas suspeitas para conferência manual. Clique em 'Comprar/ver preço' para reabrir a busca com rota, datas e 2 adultos e confirmar no Google Flights antes de qualquer compra.",
        "query_budget": {
            "max_queries_per_run": MAX_QUERIES_PER_RUN,
            "queries_attempted": len(routes),
            "stopped_for_budget": stopped_for_budget,
        },
        "best_destination": best["destination"] if best else None,
        "best_destination_label": best["label"] if best else None,
        "best_depart_date": best["depart_date"] if best else None,
        "best_return_date": best["return_date"] if best else None,
        "best_price_brl": best["cheapest"]["price_brl"] if best else None,
        "routes": routes,
        "suspicious_fares": suspicious_fares,
    }
    payload["alert"] = alert_from_route(best, suspicious_fares)
    payload["price_history"] = merge_history(previous, payload, now)
    payload["price_history_summary"] = history_summary(payload["price_history"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    previous_best = previous.get("best_price_brl") if isinstance(previous, dict) else None
    current_best = payload.get("best_price_brl")
    if current_best:
        print(
            f"Melhor tarifa atual para 2 pessoas: {format_brl(current_best)} para "
            f"{payload['best_destination_label']} ({payload['best_destination']}) "
            f"em {payload['best_depart_date']} → {payload['best_return_date']}."
        )
    else:
        print("A consulta de voos rodou, mas nenhuma tarifa válida foi capturada agora. O site mostra as rotas para nova tentativa automática.")
    if previous_best and current_best and current_best != previous_best:
        direction = "caiu" if current_best < previous_best else "subiu"
        print(f"Preço {direction}: antes {format_brl(previous_best)} → agora {format_brl(current_best)}.")
    if suspicious_fares:
        print(f"Há {len(suspicious_fares)} tarifa(s) suspeita(s) para conferência manual.")
    print(f"Updated {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
