import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import build, parse_autocentrum, parse_epetrol  # noqa: E402

# Fragment strony autocentrum.pl/paliwa/ceny-paliw (układ z 19.11.2026)
AUTOCENTRUM = """
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","name":"Aktualne ceny paliw według rodzaju",
"itemListElement":[
{"@type":"ListItem","position":1,"item":{"@type":"Thing","name":"95","description":"Średnia cena 95 w Polsce: 5.93 zł/l"}},
{"@type":"ListItem","position":2,"item":{"@type":"Thing","name":"98","description":"Średnia cena 98 w Polsce: 6.48 zł/l"}},
{"@type":"ListItem","position":3,"item":{"@type":"Thing","name":"ON","description":"Średnia cena ON w Polsce: 7.46 zł/l"}},
{"@type":"ListItem","position":4,"item":{"@type":"Thing","name":"ON premium","description":"Średnia cena ON premium w Polsce: 7.54 zł/l"}},
{"@type":"ListItem","position":5,"item":{"@type":"Thing","name":"LPG","description":"Średnia cena LPG w Polsce: 3.91 zł/l"}}]}</script>
<script type="application/ld+json">{"@type":"CollectionPage","mainEntity":{"@type":"ItemList","itemListElement":[]}}</script>
<script type="application/ld+json">to nie jest json</script>
"""

# Fragment strony e-petrol.pl (tekst tabel)
EPETROL = """
<div>Na podstawie obwieszczenia Ministra Energii ... Pb 95 6,02 5,99 5,97</div>
<table><caption>Średnie ceny detaliczne paliw w Polsce</caption>
<tr><th>Aktualizacja</th><th>Pb 98</th><th>Pb 95</th><th>ON</th><th>LPG</th></tr>
<tr><td>2026-11-18</td><td>6,64</td><td>5,99</td><td>7,54</td><td>3,96</td></tr>
<tr><td>2026-11-10</td><td>6,67</td><td>6,04</td><td>7,72</td><td>3,92</td></tr>
</table>
"""

OLD = {"updated": "2026-11-18", "prices": {"pb95": 7.09, "pb98": 7.99, "on": 7.51, "lpg": 3.16, "ev": 0.88}}


class ParseTest(unittest.TestCase):
    def test_autocentrum(self):
        self.assertEqual(parse_autocentrum(AUTOCENTRUM), {"pb95": 5.93, "pb98": 6.48, "on": 7.46, "lpg": 3.91})

    def test_autocentrum_changed_layout(self):
        self.assertEqual(parse_autocentrum("<html><body>Ceny paliw</body></html>"), {})

    def test_epetrol(self):
        prices, day = parse_epetrol(EPETROL)
        self.assertEqual(day, "2026-11-18")
        self.assertEqual(prices, {"pb98": 6.64, "pb95": 5.99, "on": 7.54, "lpg": 3.96})

    def test_epetrol_missing_table(self):
        self.assertEqual(parse_epetrol("<p>403 Forbidden</p>"), ({}, None))


class BuildTest(unittest.TestCase):
    def test_fresh_prices(self):
        fresh = {"pb95": 5.93, "pb98": 6.48, "on": 7.46, "lpg": 3.91}
        out = build(OLD, fresh, {f: "autocentrum.pl" for f in fresh}, None, "2026-11-19")
        self.assertEqual(out["prices"]["pb95"], 5.93)
        self.assertEqual(out["updated"], "2026-11-19")
        self.assertFalse(out["stale"])
        self.assertEqual(out["prices"]["ev"], 0.88)

    def test_sources_down_keeps_real_date(self):
        prev = build(OLD, {"pb95": 5.93, "pb98": 6.48, "on": 7.46, "lpg": 3.91}, {f: "autocentrum.pl" for f in ["pb95", "pb98", "on", "lpg"]}, None, "2026-11-19")
        out = build(prev, {}, {}, None, "2026-11-21")
        self.assertEqual(out["updated"], "2026-11-19")  # nie udaje, że to ceny z 21.11
        self.assertFalse(out["stale"])  # 2 dni to jeszcze nie „nieaktualne”
        out = build(prev, {}, {}, None, "2026-11-25")
        self.assertTrue(out["stale"])

    def test_old_file_without_dates_is_stale(self):
        out = build(OLD, {}, {}, None, "2026-11-19")
        self.assertIsNone(out["updated"])
        self.assertTrue(out["stale"])
        self.assertEqual(out["prices"]["pb95"], 7.09)

    def test_epetrol_date_used(self):
        fresh = {"pb95": 5.99, "pb98": 6.64, "on": 7.54, "lpg": 3.96}
        out = build(OLD, fresh, {f: "e-petrol.pl" for f in fresh}, "2026-11-18", "2026-11-19")
        self.assertEqual(out["updated"], "2026-11-18")


if __name__ == "__main__":
    unittest.main()
