#!/usr/bin/env python3
"""Send fare alerts from data/flights.json to Telegram."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FLIGHTS_PATH = ROOT / "data" / "flights.json"
STATE_PATH = ROOT / "data" / "alert_state.json"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def format_brl(value: int | None) -> str:
    if value is None:
        return "R$—"
    return f"R${value:,}".replace(",", ".")


# Re-notify only on a real improvement. Google Flights jitters by a few reais between
# runs, and at 4 runs/day an equality check would ping on every wobble — the exact
# notification fatigue this alert is meant to replace.
LEVEL_RANK = {"none": 0, "suspicious": 1, "alert": 2, "urgent": 3}
MIN_DROP_BRL = 100


def alert_key(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": alert.get("level"),
        "price_brl": alert.get("price_brl"),
        "destination": alert.get("destination"),
        "depart_date": alert.get("depart_date"),
    }


def already_notified(alert: dict[str, Any], state: dict[str, Any]) -> bool:
    """True when this alert is not a meaningful improvement over the last one sent."""
    last = state.get("last_notified")
    if not isinstance(last, dict):
        return False

    if LEVEL_RANK.get(str(alert.get("level")), 0) > LEVEL_RANK.get(str(last.get("level")), 0):
        return False  # escalated (e.g. alert -> urgent): always worth a ping

    price = alert.get("price_brl")
    last_price = last.get("price_brl")
    if not isinstance(price, int) or not isinstance(last_price, int):
        return alert_key(alert) == last

    # A different route/date only matters if it is actually cheaper.
    return price > last_price - MIN_DROP_BRL


def stops_label(value: Any) -> str:
    if isinstance(value, int):
        if value == 0:
            return "direto"
        if value == 1:
            return "1 parada"
        return f"{value} paradas"
    return str(value or "não capturado")


def level_label(level: str) -> str:
    return {
        "urgent": "URGENTE",
        "alert": "ALERTA",
        "suspicious": "CONFIRMAR MANUALMENTE",
    }.get(level, level.upper())


def build_message(payload: dict[str, Any]) -> str:
    alert = payload.get("alert") or {}
    origin = payload.get("origin") or "REC"
    destination = alert.get("destination") or "—"
    lines = [
        f"{level_label(str(alert.get('level') or 'alert'))}: passagem REC → Europa",
        "",
        alert.get("message") or "Tarifa encontrada pelo monitor.",
        "",
        f"Preço total para 2 pessoas: {format_brl(alert.get('price_brl'))}",
        f"Rota: {origin} → {destination}",
        f"Ida: {alert.get('depart_date') or '—'}",
        f"Volta: {alert.get('return_date') or '—'}",
        f"Companhia: {alert.get('airline') or 'não capturada'}",
        f"Paradas: {stops_label(alert.get('stops'))}",
        f"Link Google Flights: {alert.get('url') or payload.get('source_url') or 'https://www.google.com/travel/flights'}",
    ]
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(TELEGRAM_API.format(token=token), data=data, method="POST")
    with urlopen(request, timeout=20) as response:
        response.read()


def save_state(alert: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"last_notified": alert_key(alert)}, indent=2, ensure_ascii=False) + "\n"
    )


def main() -> int:
    payload = load_json(FLIGHTS_PATH)
    alert = payload.get("alert") or {}
    if alert.get("level") in (None, "none"):
        return 0

    state = load_json(STATE_PATH)
    if already_notified(alert, state):
        return 0

    message = build_message(payload)
    if os.environ.get("DRY_RUN") == "1":
        print(message)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return 0

    send_telegram(token, chat_id, message)
    save_state(alert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
