#!/usr/bin/env python3
"""
Scraper cen paliw — Polska
Źródła: e-petrol.pl (ceny detaliczne) + cenypaliw.fyi (backup)
Zapisuje wynik do: data/prices.json
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Instalacja zależności...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup

OUTPUT_FILE = Path(__file__).parent / "data" / "prices.json"
OUTPUT_FILE.parent.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
}

# ─── Źródło 1: e-petrol.pl ────────────────────────────────────────────────────

def scrape_epetrol():
    """
    Scrape średnich ogólnopolskich cen detalicznych z e-petrol.pl.
    Strona publikuje dane w tabeli widocznej na stronie głównej.
    """
    url = "https://www.e-petrol.pl/notowania/rynek-krajowy/ceny-stacje-paliw"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Szukamy bloku z cenami — różne selektory dla różnych layoutów strony
        prices = {}

        # Próba 1: tabela z klasą zawierającą "ceny" lub "prices"
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if not cells:
                    continue
                text = " ".join(cells).lower()
                price = extract_price(cells)
                if price is None:
                    continue
                if "pb95" in text or "95" in text and "benz" in text:
                    prices["pb95"] = price
                elif "pb98" in text or "98" in text and "benz" in text:
                    prices["pb98"] = price
                elif "on" in text or "diesel" in text or "napędowy" in text:
                    prices["on"] = price
                elif "lpg" in text or "autogaz" in text:
                    prices["lpg"] = price

        # Próba 2: elementy z atrybutem data- lub specyficzne div-y
        if not prices:
            for el in soup.find_all(["div", "span", "td"], class_=re.compile(r"(price|cena|fuel|paliwo)", re.I)):
                txt = el.get_text(strip=True)
                price = extract_price_from_string(txt)
                if price and 2.0 < price < 15.0:
                    parent_text = el.parent.get_text(strip=True).lower() if el.parent else ""
                    if "95" in parent_text:
                        prices.setdefault("pb95", price)
                    elif "98" in parent_text:
                        prices.setdefault("pb98", price)
                    elif "on" in parent_text or "diesel" in parent_text:
                        prices.setdefault("on", price)
                    elif "lpg" in parent_text:
                        prices.setdefault("lpg", price)

        if len(prices) >= 3:
            print(f"  [e-petrol.pl] OK: {prices}")
            return prices
        else:
            print(f"  [e-petrol.pl] Za mało danych ({prices}), próbuję backup...")
            return None

    except Exception as e:
        print(f"  [e-petrol.pl] Błąd: {e}")
        return None


# ─── Źródło 2: cenypaliw.fyi ─────────────────────────────────────────────────

def scrape_cenypaliw_fyi():
    """
    Scrape z cenypaliw.fyi — strona wyświetla hurtowe ceny Orlen z VAT.
    Dane są w elementach HTML z atrybutami data- lub w widocznych blokach.
    """
    url = "https://cenypaliw.fyi/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        prices = {}

        # Szukamy bloków z cenami — strona używa kart z nazwą paliwa i ceną
        text = soup.get_text()
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            ll = line.lower()
            # Sprawdzamy czy linia zawiera nazwę paliwa, a następna zawiera cenę
            context = " ".join(lines[max(0,i-2):i+3]).lower()
            price = extract_price_from_string(line)
            if price and 1.0 < price < 15.0:
                if "pb95" in context or ("95" in context and "benz" in context):
                    prices.setdefault("pb95", price)
                elif "pb98" in context or ("98" in context and "benz" in context):
                    prices.setdefault("pb98", price)
                elif "on" in context or "diesel" in context or "napędowy" in context:
                    prices.setdefault("on", price)
                elif "lpg" in context:
                    prices.setdefault("lpg", price)

        if len(prices) >= 2:
            print(f"  [cenypaliw.fyi] OK: {prices}")
            return prices
        print(f"  [cenypaliw.fyi] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [cenypaliw.fyi] Błąd: {e}")
        return None


# ─── Źródło 3: GUS (fallback tygodniowy) ─────────────────────────────────────

def scrape_autocentrum():
    """
    Autocentrum.pl — czytelna strona z cenami paliw w Polsce.
    """
    urls = {
        "pb95": "https://www.autocentrum.pl/paliwa/ceny-paliw/pb/",
        "pb98": "https://www.autocentrum.pl/paliwa/ceny-paliw/pb98/",
        "on":   "https://www.autocentrum.pl/paliwa/ceny-paliw/on/",
        "lpg":  "https://www.autocentrum.pl/paliwa/ceny-paliw/lpg/",
    }
    prices = {}
    for fuel, url in urls.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # Szukamy największej liczby wyglądającej jak cena paliwa
            candidates = []
            for el in soup.find_all(["strong", "b", "span", "div", "p"]):
                p = extract_price_from_string(el.get_text(strip=True))
                if p and 1.0 < p < 15.0:
                    candidates.append(p)
            if candidates:
                # Bierzemy medianę jako najbardziej wiarygodną
                candidates.sort()
                prices[fuel] = candidates[len(candidates)//2]
        except Exception as e:
            print(f"  [autocentrum] {fuel}: {e}")
    if prices:
        print(f"  [autocentrum.pl] OK: {prices}")
    return prices if len(prices) >= 2 else None


# ─── Pomocnicze ───────────────────────────────────────────────────────────────

def extract_price(cells):
    """Wyodrębnij cenę z listy komórek tabeli."""
    for cell in cells:
        p = extract_price_from_string(cell)
        if p and 1.0 < p < 15.0:
            return p
    return None


def extract_price_from_string(s):
    """Wyodrębnij liczbę zmiennoprzecinkową z ciągu znaków (format polski i angielski)."""
    if not s:
        return None
    # Zamień przecinek na kropkę, usuń spacje jako separator tysięcy
    cleaned = re.sub(r"\s", "", s)
    # Znajdź liczby w formacie X,XX lub X.XX
    matches = re.findall(r"\b(\d{1,2}[,\.]\d{2})\b", cleaned)
    for m in matches:
        try:
            val = float(m.replace(",", "."))
            if 1.0 < val < 15.0:
                return round(val, 2)
        except ValueError:
            pass
    return None


def merge_prices(*sources):
    """Połącz wyniki z wielu źródeł, preferując pierwsze niepuste."""
    result = {}
    for src in sources:
        if not src:
            continue
        for fuel, price in src.items():
            if fuel not in result:
                result[fuel] = price
    return result


def load_previous():
    """Wczytaj poprzedni plik JSON jako fallback."""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ─── Główna funkcja ───────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print(f"Scraper cen paliw — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # Próbujemy źródeł po kolei
    print("\n[1/3] e-petrol.pl...")
    src1 = scrape_epetrol()

    print("\n[2/3] cenypaliw.fyi...")
    src2 = scrape_cenypaliw_fyi()

    print("\n[3/3] autocentrum.pl...")
    src3 = scrape_autocentrum()

    merged = merge_prices(src1, src2, src3)

    # Uzupełniamy brakujące paliwa z poprzedniego dnia
    previous = load_previous()
    prev_prices = previous.get("prices", {})

    fuels = ["pb95", "pb98", "on", "lpg"]
    # Wartości awaryjne (ceny z dnia wdrożenia) — aktualizuj przy pierwszym uruchomieniu
    fallback = {"pb95": 6.27, "pb98": 6.88, "on": 7.83, "lpg": 3.74}

    final_prices = {}
    sources_used = {}
    for fuel in fuels:
        if fuel in merged:
            final_prices[fuel] = merged[fuel]
            # Ustal które źródło dostarczyło daną cenę
            if src1 and fuel in src1:
                sources_used[fuel] = "e-petrol.pl"
            elif src2 and fuel in src2:
                sources_used[fuel] = "cenypaliw.fyi"
            elif src3 and fuel in src3:
                sources_used[fuel] = "autocentrum.pl"
        elif fuel in prev_prices:
            final_prices[fuel] = prev_prices[fuel]
            sources_used[fuel] = "poprzedni dzień (cache)"
        else:
            final_prices[fuel] = fallback[fuel]
            sources_used[fuel] = "wartość awaryjna"

    # EV — cena prądu jest stabilna, użytkownik ustawia własną
    final_prices["ev"] = prev_prices.get("ev", 0.88)
    sources_used["ev"] = "stała (zmień ręcznie)"

    output = {
        "updated": date.today().isoformat(),
        "updated_ts": datetime.now().isoformat(),
        "prices": final_prices,
        "sources": sources_used,
        "currency": "PLN",
        "unit": {
            "pb95": "l", "pb98": "l", "on": "l", "lpg": "l", "ev": "kWh"
        }
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print("WYNIK:")
    for fuel in fuels + ["ev"]:
        print(f"  {fuel.upper():6} {final_prices[fuel]:.2f} zł  ({sources_used[fuel]})")
    print(f"\nZapisano: {OUTPUT_FILE}")
    print("=" * 50)

    # Zwróć błąd jeśli nie udało się pobrać żadnej ceny ze źródeł
    if not any([src1, src2, src3]):
        print("\nUWAGA: Wszystkie źródła niedostępne — użyto danych z cache/fallback.")
        sys.exit(1)  # GitHub Actions oznaczy run jako warning


if __name__ == "__main__":
    main()
