#!/usr/bin/env python3
"""
Średnie ceny paliw w Polsce (detaliczne, zł/l) → data/prices.json

Źródła, po kolei:
  1. autocentrum.pl — średnie ceny w Polsce z danych strukturalnych strony (JSON-LD)
  2. e-petrol.pl    — tabela „Średnie ceny detaliczne paliw w Polsce”

Gdy żadne źródło nie odpowie, zostają poprzednie ceny razem z ich prawdziwą datą,
a w pliku pojawia się "stale": true. Nigdy nie oznaczamy starych cen jako dzisiejszych.
"""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = Path(__file__).parent / "data" / "prices.json"
FUELS = ["pb95", "pb98", "on", "lpg"]
STALE_AFTER_DAYS = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

AUTOCENTRUM_URL = "https://www.autocentrum.pl/paliwa/ceny-paliw/"
EPETROL_URL = "https://www.e-petrol.pl/notowania/rynek-krajowy/ceny-stacje-paliw"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _sane(prices: dict) -> dict:
    """Odrzuca wartości spoza rozsądnego zakresu cen detalicznych."""
    return {k: round(v, 2) for k, v in prices.items() if k in FUELS and 2.0 < v < 12.0}


# ─── Parsowanie (bez sieci, testowalne) ─────────────────────────────────────

AUTOCENTRUM_NAMES = {"95": "pb95", "98": "pb98", "ON": "on", "LPG": "lpg"}


def parse_autocentrum(html: str) -> dict:
    """Średnie ceny z bloku JSON-LD „Aktualne ceny paliw według rodzaju”."""
    prices = {}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        candidates = [data]
        if isinstance(data, dict) and isinstance(data.get("mainEntity"), dict):
            candidates.append(data["mainEntity"])
        for lst in candidates:
            if not isinstance(lst, dict) or lst.get("@type") != "ItemList":
                continue
            for el in lst.get("itemListElement", []):
                item = el.get("item", {}) if isinstance(el, dict) else {}
                fuel = AUTOCENTRUM_NAMES.get(str(item.get("name", "")).strip())
                m = re.search(r"(\d+[.,]\d+)\s*zł", str(item.get("description", "")))
                if fuel and m:
                    prices.setdefault(fuel, _num(m.group(1)))
    return _sane(prices)


def parse_epetrol(html: str) -> tuple:
    """Najnowszy wiersz tabeli „Średnie ceny detaliczne paliw w Polsce” (Pb 98, Pb 95, ON, LPG) i jego data."""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = re.search(
        r"Średnie ceny detaliczne paliw w Polsce\s+Aktualizacja\s+Pb ?98\s+Pb ?95\s+ON\s+LPG\s+"
        r"(\d{4}-\d{2}-\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})",
        text,
    )
    if not m:
        return {}, None
    prices = {"pb98": _num(m.group(2)), "pb95": _num(m.group(3)), "on": _num(m.group(4)), "lpg": _num(m.group(5))}
    return _sane(prices), m.group(1)


def build(previous: dict, fresh: dict, fresh_sources: dict, fresh_date, today: str) -> dict:
    """Świeże ceny tam, gdzie są; reszta z poprzedniego pliku razem z jej prawdziwą datą."""
    prev_prices = previous.get("prices", {})
    prev_dates = previous.get("as_of") or {}
    prices, sources, as_of = {}, {}, {}
    for f in FUELS:
        if f in fresh:
            prices[f], sources[f], as_of[f] = fresh[f], fresh_sources[f], fresh_date or today
        elif f in prev_prices:
            prices[f] = prev_prices[f]
            sources[f] = "poprzednie dane (źródła niedostępne)"
            as_of[f] = prev_dates.get(f)
    prices["ev"] = prev_prices.get("ev", 0.88)
    sources["ev"] = "stała (zmień ręcznie)"
    dated = [d for d in as_of.values() if d]
    updated = min(dated) if dated else None  # data najstarszej ceny — nie udajemy świeżości
    stale = updated is None or (date.fromisoformat(today) - date.fromisoformat(updated)).days > STALE_AFTER_DAYS
    return {
        "updated": updated,
        "checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stale": stale,
        "prices": prices,
        "as_of": as_of,
        "sources": sources,
        "currency": "PLN",
        "unit": {"pb95": "l", "pb98": "l", "on": "l", "lpg": "l", "ev": "kWh"},
        "note": "Średnie ceny detaliczne paliw w Polsce",
    }


# ─── Pobieranie ─────────────────────────────────────────────────────────────

def fetch(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return r.text
    except Exception as e:  # każde źródło może zawieść — próbujemy następnego
        print(f"  błąd: {e}")
        return None


def load_previous() -> dict:
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    today = date.today().isoformat()
    print(f"Ceny paliw — {datetime.now():%Y-%m-%d %H:%M}")
    fresh, fresh_sources, fresh_date = {}, {}, None

    print("[1/2] autocentrum.pl")
    html = fetch(AUTOCENTRUM_URL)
    if html:
        p = parse_autocentrum(html)
        print(f"  {p or 'brak cen na stronie'}")
        for f, v in p.items():
            fresh[f], fresh_sources[f] = v, "autocentrum.pl"

    if any(f not in fresh for f in FUELS):
        print("[2/2] e-petrol.pl")
        html = fetch(EPETROL_URL)
        if html:
            p, d = parse_epetrol(html)
            print(f"  {p or 'brak tabeli na stronie'} {d or ''}")
            if p and not fresh:
                fresh_date = d  # tylko e-petrol: data z jego tabeli
            for f, v in p.items():
                if f not in fresh:
                    fresh[f], fresh_sources[f] = v, "e-petrol.pl"

    out = build(load_previous(), fresh, fresh_sources, fresh_date, today)
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for f in FUELS + ["ev"]:
        if f in out["prices"]:
            print(f"  {f.upper():5} {out['prices'][f]:.2f} zł  ({out['sources'][f]}, {out['as_of'].get(f, '-')})")
    if out["stale"]:
        print("UWAGA: ceny są nieaktualne — żadne źródło nie dało świeżych danych.")


if __name__ == "__main__":
    main()
