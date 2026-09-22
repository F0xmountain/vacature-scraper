"""Zelftest: draait elke bron één keer live en rapporteert wat werkt.

    python check.py

Schrijft niets weg: state.json en de output-map blijven ongemoeid, dus je kunt
dit zo vaak draaien als je wilt. Duurt circa één tot twee minuten, vooral door
de vacatureborden.

Als een bron nul resultaten geeft, wordt de opgehaalde pagina weggeschreven naar
debug/ zodat te zien is wat er veranderd is.
"""
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
DEBUG = HIER / "debug"


def kop(tekst):
    print(f"\n{tekst}")
    print("-" * len(tekst))


def check_python():
    kop("Python")
    ok = sys.version_info >= (3, 10)
    v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"{'OK  ' if ok else 'FOUT'} Python {v}" + ("" if ok else "  (3.10 of hoger nodig)"))
    return ok


def check_deps():
    kop("Pakketten")
    nodig = {
        "jobspy": "python-jobspy",
        "pandas": "pandas",
        "openpyxl": "openpyxl",
        "yaml": "PyYAML",
        "requests": "requests",
        "bs4": "beautifulsoup4",
    }
    ontbreekt = []
    for mod, pakket in nodig.items():
        try:
            __import__(mod)
            print(f"OK   {pakket}")
        except ImportError:
            print(f"FOUT {pakket} ontbreekt")
            ontbreekt.append(pakket)
    if ontbreekt:
        print("\n  Oplossing: pip install -r requirements.txt")
    return not ontbreekt


def _toon(naam, rows, duur, fout=None):
    if fout:
        print(f"FOUT {naam}: {fout}")
        return
    if not rows:
        print(f"LEEG {naam}: geen resultaten ({duur:.0f}s)")
        return
    r = rows[0]
    print(f"OK   {naam}: {len(rows)} vacatures ({duur:.0f}s)")
    print(f"       {r['functie'][:48]} | {r['bedrijf'][:22]} | {r['locatie'][:18] or 'geen locatie'}")


def _bewaar_debug(naam, html):
    try:
        DEBUG.mkdir(exist_ok=True)
        pad = DEBUG / f"{naam}.html"
        pad.write_text(html, encoding="utf-8")
        print(f"       pagina bewaard in debug/{pad.name}")
    except Exception:
        pass


def check_boards(cfg):
    """Eén zoekterm, kleine hoeveelheid: alleen om te zien of de borden antwoorden."""
    kop("Vacatureborden (LinkedIn, Indeed, Glassdoor)")
    b = cfg.get("boards") or {}
    term = (cfg.get("zoektermen") or ["financial analyst"])[0]
    print(f"Testterm: '{term}'. Dit duurt even.")
    mini = dict(cfg)
    mini["zoektermen"] = [term]
    mini["boards"] = {**b, "resultaten_per_term": 5, "max_uren_oud": 168}
    t0 = time.time()
    try:
        from sources_boards import fetch_boards
        rows = fetch_boards(mini)
        _toon("borden", rows, time.time() - t0)
        if not rows:
            print("       Mogelijk rate limiting (429). Probeer het later opnieuw.")
        return rows
    except Exception as e:
        _toon("borden", [], time.time() - t0, fout=e)
        return []


def check_magnetme(cfg):
    kop("Magnet.me")
    m = cfg.get("magnetme") or {}
    if not m.get("paden"):
        print("OVER Geen paden geconfigureerd")
        return []
    mini = dict(cfg)
    mini["magnetme"] = {**m, "paden": m["paden"][:1], "paginas": 1}
    t0 = time.time()
    try:
        from sources_magnetme import fetch_magnetme
        rows = fetch_magnetme(mini)
        _toon("magnet.me", rows, time.time() - t0)
        if not rows:
            _dump_pagina(f"https://magnet.me/nl-NL/{m['paden'][0]}", "magnetme")
        return rows
    except Exception as e:
        _toon("magnet.me", [], time.time() - t0, fout=e)
        return []


def check_ats(cfg):
    kop("Careers-feeds (Recruitee, Greenhouse, Lever, Workday)")
    a = cfg.get("ats") or {}
    if not any(a.get(k) for k in ("recruitee", "greenhouse", "lever", "workday")):
        print("OVER Geen feeds geconfigureerd")
        return []
    t0 = time.time()
    try:
        from sources_ats import fetch_ats
        rows = fetch_ats(cfg)
        _toon("careers-feeds", rows, time.time() - t0)
        return rows
    except Exception as e:
        _toon("careers-feeds", [], time.time() - t0, fout=e)
        return []


def check_werkenbij(cfg):
    kop("Eigen careers-sites")
    w = cfg.get("werkenbij") or {}
    sites = w.get("sites") or []
    if not sites:
        print("OVER Geen sites geconfigureerd")
        return []
    alle = []
    for site in sites:
        t0 = time.time()
        try:
            from sources_html import _fetch_site
            rows = _fetch_site(site)
            _toon(site.get("naam", "?"), rows, time.time() - t0)
            if not rows:
                _dump_pagina(site["url"], site.get("naam", "site").lower())
            alle += rows
        except Exception as e:
            _toon(site.get("naam", "?"), [], time.time() - t0, fout=e)
        time.sleep(1)
    return alle


def _dump_pagina(url, naam):
    try:
        import requests
        from sources_html import HEADERS
        r = requests.get(url, headers=HEADERS, timeout=20)
        _bewaar_debug(naam, r.text)
    except Exception:
        pass


def check_filter(cfg, jobs):
    kop("Filter")
    if not jobs:
        print("OVER Geen vacatures opgehaald, filter niet getest")
        return
    from filters import apply_filters
    from store import dedupe
    uniek = dedupe(jobs)
    kept, stats = apply_filters(uniek, cfg)
    print(f"Opgehaald: {len(jobs)}  |  na ontdubbelen: {len(uniek)}")
    print(f"Gedropt op titel: {stats['titel']}  |  gedropt op locatie: {stats['locatie']}")
    print(f"Blijft over: {len(kept)}")
    if kept:
        print("\nVoorbeelden van wat er doorheen komt:")
        for r in kept[:5]:
            flags = f"  [{r['flags']}]" if r.get("flags") else ""
            print(f"  {r['functie'][:44]:<44} {r['bedrijf'][:20]:<20}{flags}")


def main():
    print("Zelftest vacature-scraper. Er wordt niets weggeschreven.")
    if not check_python() or not check_deps():
        print("\nLos eerst het bovenstaande op en draai check.py opnieuw.")
        return

    import yaml
    cfg = yaml.safe_load((HIER / "config.yaml").read_text(encoding="utf-8"))

    jobs = []
    jobs += check_boards(cfg)
    jobs += check_magnetme(cfg)
    jobs += check_ats(cfg)
    jobs += check_werkenbij(cfg)
    check_filter(cfg, jobs)

    kop("Conclusie")
    if jobs:
        print("Er komt data binnen en het filter werkt.")
        print("Volgende stap: python scraper.py --dry-run")
    else:
        print("Geen enkele bron gaf resultaat. Check je internetverbinding;")
        print("blijft het leeg, stuur de uitvoer hierboven plus de debug-map door.")


if __name__ == "__main__":
    main()
