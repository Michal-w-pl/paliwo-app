#!/usr/bin/env python3
"""
Scraper cen paliw — Polska
Główne źródło: cenypaliw.fyi (hurtowe PKN Orlen z VAT)
Backup: e-petrol.pl, orlen.pl
Zapisuje wynik do: data/prices.json
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

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
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── Źródło 1: cenypaliw.fyi ─────────────────────────────────────────────────

def scrape_cenypaliw_fyi():
    url = "https://cenypaliw.fyi/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        prices = {}

        # Tabela: | Rodzaj paliwa | Cena bez VAT | Cena z VAT (23%) | Źródło |
        # Kolejność wierszy: ON, PB 95, PB 98, ON Ekoterm, Ropa Brent, USD/PLN
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue
                name = cells[0].strip()           # np. "ON", "PB 95", "ON Ekoterm"
                name_l = name.lower()
                price_vat = parse_price(cells[2]) # kolumna "Cena z VAT"
                if price_vat is None:
                    continue

                # Dopasowanie ŚCISŁE — "ON Ekoterm" nie może trafić do klucza "on"
                if re.fullmatch(r"on", name_l):
                    prices["on"] = price_vat
                elif re.search(r"pb\s*95", name_l):
                    prices["pb95"] = price_vat
                elif re.search(r"pb\s*98", name_l):
                    prices["pb98"] = price_vat
                elif re.search(r"lpg", name_l):
                    prices["lpg"] = price_vat
                # "ON Ekoterm", "Ropa Brent", "USD/PLN" — celowo pomijamy

        if len(prices) >= 2:
            print(f"  [cenypaliw.fyi tabela] OK: {prices}")
            return prices

        # Fallback: regex w tekście — szukamy konkretnych zdań ze strony
        # "Hurtowa cena oleju napędowego wynosi X.XX PLN/litr bez VAT (Y.YY PLN/litr z VAT)"
        text = soup.get_text()
        m_on  = re.search(r"oleju napędowego wynosi[\s\S]{1,60}?\((\d+\.\d+)\s*PLN/litr z VAT\)", text)
        m_95  = re.search(r"bezołowiowej 95 wynosi[\s\S]{1,60}?\((\d+\.\d+)\s*PLN/litr z VAT\)", text)
        m_98  = re.search(r"bezołowiowej 98 wynosi[\s\S]{1,60}?\((\d+\.\d+)\s*PLN/litr z VAT\)", text)

        if m_on:  prices.setdefault("on",   float(m_on.group(1)))
        if m_95:  prices.setdefault("pb95", float(m_95.group(1)))
        if m_98:  prices.setdefault("pb98", float(m_98.group(1)))

        if len(prices) >= 2:
            print(f"  [cenypaliw.fyi regex] OK: {prices}")
            return prices

        print(f"  [cenypaliw.fyi] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [cenypaliw.fyi] Błąd: {e}")
        return None


# ─── Źródło 2: e-petrol.pl ───────────────────────────────────────────────────

def scrape_epetrol():
    url = "https://www.e-petrol.pl/"
    headers = {**HEADERS, "Referer": "https://www.google.pl/"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text()
        prices = {}
        patterns = {
            "pb95": r"[Pp][Bb]?\s*95[^0-9]{0,20}(\d+[,\.]\d+)",
            "pb98": r"[Pp][Bb]?\s*98[^0-9]{0,20}(\d+[,\.]\d+)",
            "on":   r"\bON\b[^0-9]{0,20}(\d+[,\.]\d+)",
            "lpg":  r"\bLPG\b[^0-9]{0,20}(\d+[,\.]\d+)",
        }
        for fuel, pattern in patterns.items():
            m = re.search(pattern, text)
            if m:
                val = float(m.group(1).replace(",", "."))
                if 1.0 < val < 15.0:
                    prices[fuel] = val

        if len(prices) >= 2:
            print(f"  [e-petrol.pl] OK: {prices}")
            return prices

        print(f"  [e-petrol.pl] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [e-petrol.pl] Błąd: {e}")
        return None


# ─── Źródło 3: orlen.pl ──────────────────────────────────────────────────────

def scrape_orlen():
    url = "https://www.orlen.pl/pl/dla-biznesu/hurtowe-ceny-paliw"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text()
        prices = {}
        VAT = 1.08
        m95  = re.search(r"[Ee]urosuper\s*95[^\d]{0,30}(\d+[,\.]\d+)", text)
        m98  = re.search(r"[Ss]uper\s*98[^\d]{0,30}(\d+[,\.]\d+)", text)
        mon  = re.search(r"[Ee]urodiesel[^\d]{0,30}(\d+[,\.]\d+)", text)
        mlpg = re.search(r"[Aa]utogas[^\d]{0,30}(\d+[,\.]\d+)", text)
        if m95:  prices["pb95"] = round(float(m95.group(1).replace(",","."))  * VAT, 2)
        if m98:  prices["pb98"] = round(float(m98.group(1).replace(",","."))  * VAT, 2)
        if mon:  prices["on"]   = round(float(mon.group(1).replace(",","."))  * VAT, 2)
        if mlpg: prices["lpg"]  = round(float(mlpg.group(1).replace(",",".")) * VAT, 2)

        if len(prices) >= 2:
            print(f"  [orlen.pl] OK: {prices}")
            return prices

        print(f"  [orlen.pl] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [orlen.pl] Błąd: {e}")
        return None


# ─── Pomocnicze ───────────────────────────────────────────────────────────────

def parse_price(s):
    if not s:
        return None
    m = re.search(r"(\d+)[,\.](\d{2})", s)
    if m:
        val = float(f"{m.group(1)}.{m.group(2)}")
        if 1.0 < val < 20.0:
            return round(val, 2)
    return None


def load_previous():
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def merge(*sources):
    result = {}
    for src in sources:
        if not src:
            continue
        for fuel, price in src.items():
            if fuel not in result:
                result[fuel] = price
    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print(f"Scraper cen paliw — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 52)

    print("\n[1/3] cenypaliw.fyi...")
    src1 = scrape_cenypaliw_fyi()

    print("\n[2/3] e-petrol.pl...")
    src2 = scrape_epetrol()

    print("\n[3/3] orlen.pl...")
    src3 = scrape_orlen()

    merged = merge(src1, src2, src3)
    previous = load_previous()
    prev_prices = previous.get("prices", {})
    fallback = {"pb95": 6.27, "pb98": 6.88, "on": 7.83, "lpg": 3.74}
    fuels = ["pb95", "pb98", "on", "lpg"]

    final = {}
    sources_used = {}

    for fuel in fuels:
        if fuel in merged:
            final[fuel] = merged[fuel]
            if src1 and fuel in src1:
                sources_used[fuel] = "cenypaliw.fyi"
            elif src2 and fuel in src2:
                sources_used[fuel] = "e-petrol.pl"
            else:
                sources_used[fuel] = "orlen.pl"
        elif fuel in prev_prices:
            final[fuel] = prev_prices[fuel]
            sources_used[fuel] = "poprzedni dzień (cache)"
        else:
            final[fuel] = fallback[fuel]
            sources_used[fuel] = "wartość awaryjna"

    final["ev"] = prev_prices.get("ev", 0.88)
    sources_used["ev"] = "stała (zmień ręcznie)"

    output = {
        "updated": date.today().isoformat(),
        "updated_ts": datetime.now().isoformat(),
        "prices": final,
        "sources": sources_used,
        "currency": "PLN",
        "unit": {"pb95":"l","pb98":"l","on":"l","lpg":"l","ev":"kWh"},
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 52)
    print("WYNIK:")
    for fuel in fuels + ["ev"]:
        print(f"  {fuel.upper():6} {final[fuel]:.2f} zł  ({sources_used[fuel]})")
    print(f"\nZapisano: {OUTPUT_FILE}")
    print("=" * 52)


if __name__ == "__main__":
    main()
