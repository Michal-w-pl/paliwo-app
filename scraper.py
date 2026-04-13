#!/usr/bin/env python3
"""
Scraper maksymalnych cen paliw detalicznych — Polska
Źródło: obwieszczenie Ministra Energii (ceny detaliczne max. z VAT 8%)
Strony: e-petrol.pl, monitorpolski.gov.pl
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
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── Źródło 1: e-petrol.pl/notowania — ceny detaliczne max. z obwieszczenia ──
# Strona publikuje tabelę "Na podstawie obwieszczenia Ministra Energii"
# z cenami: Pb95, Pb98, ON — aktualizowaną codziennie

def scrape_epetrol_notowania():
    url = "https://www.e-petrol.pl/notowania/rynek-krajowy/ceny-stacje-paliw"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        prices = {}

        # Strona zawiera tabelę z datą i cenami w formacie:
        # "2026-04-14 · Pb95 · 6,12 · 6,10 · Pb98 · 6,70 · ..."
        # Szukamy wzorców "Pb95 ... X,XX" i "ON ... X,XX"
        pb95 = re.search(r"Pb95\s*[·\|•]\s*(\d+[,\.]\d+)", text)
        pb98 = re.search(r"Pb98\s*[·\|•]\s*(\d+[,\.]\d+)", text)
        on   = re.search(r"\bON\s*[·\|•]\s*(\d+[,\.]\d+)", text)
        lpg  = re.search(r"\bLPG\s*[·\|•]\s*(\d+[,\.]\d+)", text)

        if pb95: prices["pb95"] = float(pb95.group(1).replace(",", "."))
        if pb98: prices["pb98"] = float(pb98.group(1).replace(",", "."))
        if on:   prices["on"]   = float(on.group(1).replace(",", "."))
        if lpg:  prices["lpg"]  = float(lpg.group(1).replace(",", "."))

        # Walidacja — ceny detaliczne powinny być w rozsądnym zakresie
        prices = {k: v for k, v in prices.items() if 3.0 < v < 12.0}

        if len(prices) >= 2:
            print(f"  [e-petrol notowania] OK: {prices}")
            return prices

        # Fallback: szukaj liczb w sąsiedztwie nazw paliw w całym tekście
        prices = {}
        for fuel, pat in [
            ("pb95", r"[Pp]b\s*95[^\d]{0,30}?(\d+[,\.]\d{2})"),
            ("pb98", r"[Pp]b\s*98[^\d]{0,30}?(\d+[,\.]\d{2})"),
            ("on",   r"\bON\b[^\d]{0,30}?(\d+[,\.]\d{2})"),
            ("lpg",  r"\bLPG\b[^\d]{0,30}?(\d+[,\.]\d{2})"),
        ]:
            for m in re.finditer(pat, text):
                val = float(m.group(1).replace(",", "."))
                if 3.0 < val < 12.0:
                    prices.setdefault(fuel, val)
                    break

        prices = {k: v for k, v in prices.items() if 3.0 < v < 12.0}
        if len(prices) >= 2:
            print(f"  [e-petrol fallback] OK: {prices}")
            return prices

        print(f"  [e-petrol notowania] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [e-petrol notowania] Błąd: {e}")
        return None


# ─── Źródło 2: Monitor Polski — obwieszczenie Ministra Energii ───────────────
# Szukamy najnowszego obwieszczenia i wyciągamy z niego ceny max.

def scrape_monitor_polski():
    # Wyszukiwarka Monitora Polskiego — obwieszczenia ws. cen paliw 2026
    url = (
        "https://monitorpolski.gov.pl/szukaj"
        "?diary=0&typact=10&year=2026"
        "&title=sprawie+maksymalnej+ceny+paliw+ciek%C5%82ych+na+stacji+paliw"
        "&sKey=year&sOrder=desc"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Znajdź link do najnowszego obwieszczenia
        links = soup.find_all("a", href=re.compile(r"/DU/\d+/|/MP/\d+/"))
        if not links:
            # Próba alternatywna — każdy link z "cena" w tekście
            links = [a for a in soup.find_all("a") if "cen" in a.get_text().lower()]

        if not links:
            print("  [Monitor Polski] Brak linków do obwieszczenia")
            return None

        # Bierzemy pierwszy (najnowszy) link
        href = links[0].get("href", "")
        if not href.startswith("http"):
            href = "https://monitorpolski.gov.pl" + href

        r2 = requests.get(href, headers=HEADERS, timeout=20)
        r2.raise_for_status()
        text = BeautifulSoup(r2.text, "html.parser").get_text(" ", strip=True)

        prices = {}
        pb95 = re.search(r"benz[^\d]{0,50}?95[^\d]{0,50}?(\d+[,\.]\d{2})\s*z[łl]", text, re.I)
        pb98 = re.search(r"benz[^\d]{0,50}?98[^\d]{0,50}?(\d+[,\.]\d{2})\s*z[łl]", text, re.I)
        on   = re.search(r"olej[^\d]{0,50}?napęd[^\d]{0,50}?(\d+[,\.]\d{2})\s*z[łl]", text, re.I)

        if pb95: prices["pb95"] = float(pb95.group(1).replace(",", "."))
        if pb98: prices["pb98"] = float(pb98.group(1).replace(",", "."))
        if on:   prices["on"]   = float(on.group(1).replace(",", "."))

        prices = {k: v for k, v in prices.items() if 3.0 < v < 12.0}
        if len(prices) >= 2:
            print(f"  [Monitor Polski] OK: {prices}")
            return prices

        print(f"  [Monitor Polski] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [Monitor Polski] Błąd: {e}")
        return None


# ─── Źródło 3: TVN24 Biznes — artykuły o cenach paliw ───────────────────────
# TVN24 publikuje codziennie artykuł z tytułem zawierającym aktualne ceny

def scrape_tvn24():
    today = date.today()
    # Szukamy w Google News / bezpośrednio w TVN24
    search_url = (
        f"https://tvn24.pl/biznes/moto/ceny-paliw"
    )
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        prices = {}

        # TVN24 podaje ceny w formacie "Pb95 - X,XX zł za litr"
        pb95 = re.search(r"[Pp]b\s*95\s*[-–]\s*(\d+[,\.]\d{2})\s*z[łl]", text)
        pb98 = re.search(r"[Pp]b\s*98\s*[-–]\s*(\d+[,\.]\d{2})\s*z[łl]", text)
        on   = re.search(r"(?:olej napędowy|ON)\s*[-–]\s*(\d+[,\.]\d{2})\s*z[łl]", text, re.I)

        if pb95: prices["pb95"] = float(pb95.group(1).replace(",", "."))
        if pb98: prices["pb98"] = float(pb98.group(1).replace(",", "."))
        if on:   prices["on"]   = float(on.group(1).replace(",", "."))

        prices = {k: v for k, v in prices.items() if 3.0 < v < 12.0}
        if len(prices) >= 2:
            print(f"  [TVN24] OK: {prices}")
            return prices

        print(f"  [TVN24] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [TVN24] Błąd: {e}")
        return None


# ─── Źródło 4: e-petrol.pl strona główna ─────────────────────────────────────

def scrape_epetrol_home():
    url = "https://www.e-petrol.pl/"
    headers = {**HEADERS, "Referer": "https://www.google.pl/"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        prices = {}

        for fuel, pat in [
            ("pb95", r"[Pp]b\s*95[^\d]{0,20}(\d+[,\.]\d{2})"),
            ("pb98", r"[Pp]b\s*98[^\d]{0,20}(\d+[,\.]\d{2})"),
            ("on",   r"\bON\b[^\d]{0,20}(\d+[,\.]\d{2})"),
            ("lpg",  r"\bLPG\b[^\d]{0,20}(\d+[,\.]\d{2})"),
        ]:
            for m in re.finditer(pat, text):
                val = float(m.group(1).replace(",", "."))
                if 3.0 < val < 12.0:
                    prices.setdefault(fuel, val)
                    break

        if len(prices) >= 2:
            print(f"  [e-petrol home] OK: {prices}")
            return prices

        print(f"  [e-petrol home] Za mało danych: {prices}")
        return None

    except Exception as e:
        print(f"  [e-petrol home] Błąd: {e}")
        return None


# ─── Pomocnicze ───────────────────────────────────────────────────────────────

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


def source_name(fuel, src1, src2, src3, src4):
    if src1 and fuel in src1: return "e-petrol.pl/notowania"
    if src2 and fuel in src2: return "monitorpolski.gov.pl"
    if src3 and fuel in src3: return "tvn24.pl"
    if src4 and fuel in src4: return "e-petrol.pl"
    return "cache/fallback"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print(f"Scraper cen paliw (detaliczne max.) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 56)

    print("\n[1/4] e-petrol.pl/notowania (ceny max. z obwieszczenia)...")
    src1 = scrape_epetrol_notowania()

    print("\n[2/4] monitorpolski.gov.pl...")
    src2 = scrape_monitor_polski()

    print("\n[3/4] tvn24.pl/biznes/moto...")
    src3 = scrape_tvn24()

    print("\n[4/4] e-petrol.pl (strona główna)...")
    src4 = scrape_epetrol_home()

    merged = merge(src1, src2, src3, src4)
    previous = load_previous()
    prev_prices = previous.get("prices", {})

    # Wartości awaryjne — aktualne na 14.04.2026
    fallback = {"pb95": 6.12, "pb98": 6.70, "on": 7.58, "lpg": 3.80}
    fuels = ["pb95", "pb98", "on", "lpg"]

    final = {}
    sources_used = {}

    for fuel in fuels:
        if fuel in merged:
            final[fuel] = round(merged[fuel], 2)
            sources_used[fuel] = source_name(fuel, src1, src2, src3, src4)
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
        "note": "Ceny detaliczne maksymalne wg obwieszczenia Ministra Energii (VAT 8%)"
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 56)
    print("WYNIK (ceny detaliczne max., VAT 8%):")
    for fuel in fuels + ["ev"]:
        print(f"  {fuel.upper():6} {final[fuel]:.2f} zł  ({sources_used[fuel]})")
    print(f"\nZapisano: {OUTPUT_FILE}")
    print("=" * 56)

    if not merged:
        print("\nUWAGA: Wszystkie źródła niedostępne — użyto danych z cache/fallback.")


if __name__ == "__main__":
    main()
