#!/usr/bin/env python3
"""Update REC -> Europe Jan 2027 flight prices for the trip site.

Best-effort Google Flights lookup via fast-flights. Some routes may fail when
Google anti-bot checks trigger; failures are recorded in data/flights.json
instead of crashing the whole update.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROUTES = {
    "AMS": {"city": "Amsterdã", "country": "Holanda", "label": "Aeroporto de Amsterdã Schiphol"},
    "CDG": {"city": "Paris", "country": "França", "label": "Aeroporto Paris Charles de Gaulle"},
    "BRU": {"city": "Bruxelas", "country": "Bélgica", "label": "Aeroporto de Bruxelas"},
}
ORIGIN = "REC"
DEPART_DATE = "2027-01-10"
RETURN_DATE = "2027-01-25"
ADULTS = 2
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "flights.json"


def parse_brl(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


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


def query_route(dest: str) -> dict[str, Any]:
    from fast_flights import FlightData, Passengers, get_flights

    meta = ROUTES[dest]
    base = {
        "origin": ORIGIN,
        "destination": dest,
        **meta,
        "depart_date": DEPART_DATE,
        "return_date": RETURN_DATE,
        "adults": ADULTS,
        "status": "ok",
    }

    try:
        result = get_flights(
            flight_data=[
                FlightData(date=DEPART_DATE, from_airport=ORIGIN, to_airport=dest),
                FlightData(date=RETURN_DATE, from_airport=dest, to_airport=ORIGIN),
            ],
            trip="round-trip",
            passengers=Passengers(adults=ADULTS, children=0, infants_in_seat=0, infants_on_lap=0),
            seat="economy",
            fetch_mode="fallback",
        )
        flights = [flight_to_dict(f) for f in getattr(result, "flights", [])]
        # De-dupe by airline/departure/arrival/price.
        seen = set()
        unique = []
        for f in flights:
            key = (f.get("name"), f.get("departure"), f.get("arrival"), f.get("price"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)
        unique.sort(key=lambda f: f.get("price_brl") or 10**12)
        cheapest = unique[0] if unique else None
        return {
            **base,
            "price_level": getattr(result, "current_price", None),
            "cheapest": cheapest,
            "flights": unique[:8],
            "error": None,
        }
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
            "error": error,
        }


def main() -> int:
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text())
        except Exception:
            previous = {}

    routes = [query_route(dest) for dest in ROUTES]
    ok_routes = [r for r in routes if (r.get("cheapest") or {}).get("price_brl")]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not ok_routes and isinstance(previous, dict) and previous.get("best_price_brl"):
        # Avoid replacing useful fare data with an all-failed anti-bot run.
        previous["last_attempt_at"] = now
        previous["last_attempt_note"] = "A última consulta automática não capturou tarifas; mantendo o último preço válido."
        OUT.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + "\n")
        print(
            f"Nenhuma tarifa capturada hoje; mantive o último melhor preço: R${previous['best_price_brl']:,} "
            f"para {previous.get('best_destination_label')} ({previous.get('best_destination')}).".replace(",", ".")
        )
        print(f"Updated {OUT}")
        return 0

    best = min(ok_routes, key=lambda r: (r["cheapest"] or {})["price_brl"]) if ok_routes else None

    payload = {
        "updated_at": now,
        "origin": ORIGIN,
        "origin_label": "Recife / Guararapes–Gilberto Freyre International Airport",
        "depart_date": DEPART_DATE,
        "return_date": RETURN_DATE,
        "travelers": ADULTS,
        "currency": "BRL",
        "source_note": "Consulta automática via Google Flights/fast-flights em modo melhor esforço. Antes de comprar, confirme sempre no site da companhia aérea ou da agência.",
        "best_destination": best["destination"] if best else None,
        "best_destination_label": best["label"] if best else None,
        "best_price_brl": best["cheapest"]["price_brl"] if best else None,
        "routes": routes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    previous_best = previous.get("best_price_brl") if isinstance(previous, dict) else None
    current_best = payload.get("best_price_brl")
    if current_best:
        print(f"Melhor tarifa atual para 2 pessoas: R${current_best:,} para {payload['best_destination_label']} ({payload['best_destination']}).".replace(",", "."))
    else:
        print("A consulta de voos rodou, mas nenhuma tarifa foi capturada agora. O site mostra as rotas para nova tentativa automática.")
    if previous_best and current_best and current_best != previous_best:
        direction = "caiu" if current_best < previous_best else "subiu"
        print(f"Preço {direction}: antes R${previous_best:,} → agora R${current_best:,}.".replace(",", "."))
    print(f"Updated {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
