"""Magnet.me via de publieke, servergerenderde overzichtspagina's.

Geen login en geen browser nodig: pagina's onder magnet.me/nl-NL/banen/{stad}/{functie}
bevatten de vacaturekaarten direct in de HTML. Per kaart: bedrijf (uit het
logo-alt-attribuut), titel plus link (uit de vacature-anchor) en salaris indien
getoond. Standaard worden alleen overzichtspagina's opgehaald, wat de belasting op
een handvol requests houdt. Staat detail_beschrijving in config.yaml aan, dan wordt
per vacature ook de detailpagina opgehaald voor de omschrijving (een request per
vacature).

Een geplaatst-datum staat niet op de overzichtspagina; nieuwheid wordt via
state.json bepaald, dus dat is geen gemis.
"""
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://magnet.me/nl-NL"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
TIMEOUT = 20
VACATURE_RE = re.compile(r"/nl-NL/vacature/\d+/")
SALARIS_RE = re.compile(r"€\s?[\d.,]+(?:\s*-\s*€\s?[\d.,]+)?\s*per\s*(?:maand|jaar)")


def fetch_magnetme(cfg):
    m = cfg.get("magnetme") or {}
    paden = m.get("paden") or []
    paginas = int(m.get("paginas", 2))
    jobs = []

    for pad in paden:
        pad = pad.strip("/")
        delen = pad.split("/")
        stad = delen[1] if len(delen) >= 2 else ""
        for p in range(1, paginas + 1):
            url = f"{BASE}/{pad}?page={p}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                r.raise_for_status()
                gevonden = _parse_listing(r.text, stad)
            except Exception as e:
                print(f"[magnetme] {pad} pagina {p} mislukt: {e}")
                break
            print(f"[magnetme] {pad} pagina {p}: {len(gevonden)} vacatures")
            if not gevonden:
                break
            jobs += gevonden
            time.sleep(2)

    # Detailpagina's niet hier ophalen: dat gebeurt na het filteren en parallel
    # (sources_detail), alleen voor vacatures die de poort halen. Hier alleen de
    # vlag zetten zodat die stap weet welke vacatures een eigen detailpagina hebben.
    if cfg.get("detail_beschrijving"):
        for job in jobs:
            job["_detail"] = True
    return jobs


def _parse_listing(html, stad):
    soup = BeautifulSoup(html, "html.parser")
    out, gezien = [], set()

    for a in soup.find_all("a", href=VACATURE_RE):
        titel = a.get_text(strip=True)
        if not titel:
            continue
        href = a["href"]
        if href in gezien:
            continue
        gezien.add(href)

        kaart = a.find_parent("li") or a.find_parent("article") or a.parent
        bedrijf, salaris = "", ""
        if kaart is not None:
            logo = kaart.find("img", alt=re.compile(r"^Logo\s"))
            if logo and logo.get("alt"):
                bedrijf = logo["alt"][5:].strip()
            m = SALARIS_RE.search(kaart.get_text(" ", strip=True))
            if m:
                salaris = m.group(0)

        out.append({
            "bron": "magnetme",
            "bedrijf": bedrijf or "onbekend",
            "functie": titel,
            "locatie": stad,
            "geplaatst": "",
            "salaris": salaris,
            "url": href if href.startswith("http") else f"https://magnet.me{href}",
            "beschrijving": "",
        })

    return out
