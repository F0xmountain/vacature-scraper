"""Omschrijvingen van detailpagina's ophalen, parallel en pas nadat de vacatures
de poort zijn gepasseerd.

Waarom hier en niet in de bronmodules zelf: eerst filteren en dan pas de
omschrijvingen ophalen scheelt honderden requests die anders voor weggefilterde
vacatures zouden worden gedaan. En parallel in plaats van serieel met een seconde
pauze per stuk maakt van een lus van minuten een klus van seconden.

Bronnen met een eigen detailpagina (Magnet.me, werkenbij, en LinkedIn-vacatures
zonder omschrijving) zetten de vlag _detail op hun vacatures; ATS levert de
omschrijving al mee in de listing. De vlag wordt hier van alle jobs verwijderd
zodat hij niet in de uitvoer belandt.

Tempo per host, en waarom dat moet. Op 21-09-2026 gaf LinkedIn 279 keer een 429
in deze fase: een paar honderd detailpagina's, zes tegelijk, zonder pauze. Die
vacatures kwamen zonder functietekst binnen, en daardoor miste flag_termen de
helft van zijn werk, want dat matcht ook op de omschrijving. Magnet.me en de
werkenbij-sites gaan om tientallen requests en hebben die rem niet nodig, dus de
snelheid daar blijft zoals hij was.
"""
import concurrent.futures as cf
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import requests

from sources_tekst import uit_pagina

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
TIMEOUT = 20

# Bewust bescheiden: sneller dan serieel, maar geen stortvloed op een publieke
# site. Een mislukte detailpagina laat de omschrijving leeg, net als voorheen; de
# vacature blijft gewoon staan.
WORKERS = 6

# Per host: hoeveel tegelijk, en minimaal hoeveel seconden tussen twee requests.
# De pauze geldt over alle workers samen, niet per worker.
_TEMPO = {
    "linkedin.com": {"workers": 2, "pauze": 1.2},
}
_STANDAARD = {"workers": WORKERS, "pauze": 0.0}

# Herkansing bij een 429, net als de borden die doen bij hun zoekopdrachten.
_POGINGEN = 3
_BACKOFF_SEC = 5

# Sites die hun omschrijving in een bekend blok zetten. Zonder selector komt bij
# LinkedIn de halve pagina mee (navigatie, "meld je aan", gerelateerde vacatures)
# in plaats van de functietekst. Gematcht op URL en niet op bron, want na het
# ontdubbelen kan bron zijn samengevoegd tot "indeed, linkedin".
_SELECTORS = (
    ("linkedin.com/jobs/view", "div.show-more-less-html__markup"),
)


def _selector_voor(url):
    for sleutel, selector in _SELECTORS:
        if sleutel in (url or ""):
            return selector
    return None


def _host(url):
    """Registreerbare host, zodat www.linkedin.com en nl.linkedin.com samenvallen."""
    net = urlsplit(url or "").netloc.lower()
    delen = net.split(".")
    return ".".join(delen[-2:]) if len(delen) >= 2 else net


def _tempo_voor(host):
    return _TEMPO.get(host, _STANDAARD)


class _Pacer:
    """Houdt requests naar een host minimaal 'pauze' seconden uit elkaar.

    De wachttijd wordt onder de lock afgewikkeld, zodat het tempo over alle
    workers samen geldt en niet per worker. Bij pauze 0 doet hij niets en blijft
    het gedrag gelijk aan voorheen.
    """

    def __init__(self, pauze):
        self.pauze = pauze
        self._lock = threading.Lock()
        self._volgende = 0.0

    def wacht(self):
        if self.pauze <= 0:
            return
        with self._lock:
            nu = time.monotonic()
            if nu < self._volgende:
                time.sleep(self._volgende - nu)
                nu = time.monotonic()
            self._volgende = nu + self.pauze


def _een(job, pacer, mislukt):
    url = job.get("url") or ""
    for poging in range(1, _POGINGEN + 1):
        pacer.wacht()
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429 and poging < _POGINGEN:
                time.sleep(_BACKOFF_SEC * poging)
                continue
            r.raise_for_status()
            job["beschrijving"] = uit_pagina(r.text, _selector_voor(url))
            return
        except Exception as e:
            if poging == _POGINGEN:
                # Niet elke mislukking apart melden: dat waren er laatst 280 en
                # dan verdwijnt de samenvatting van de run uit beeld. Tellen en
                # aan het eind een regel per bron.
                mislukt[f"{job.get('bron', '?')} {type(e).__name__}"] += 1
            elif not isinstance(e, requests.HTTPError):
                time.sleep(_BACKOFF_SEC * poging)


def vul_beschrijvingen(jobs, workers=None):
    """Haalt parallel de omschrijving op voor elke job met de vlag _detail.

    Groepeert op host, zodat elke site zijn eigen tempo en parallellisme krijgt;
    de groepen draaien wel naast elkaar. De vlag wordt van alle jobs verwijderd
    (ook die er geen hebben), zodat hij niet in de uitvoer lekt. Geeft niets
    terug; de jobs worden ter plekke aangevuld.
    """
    doelen = [j for j in jobs if j.pop("_detail", False)]
    if not doelen:
        return

    per_host = defaultdict(list)
    for j in doelen:
        per_host[_host(j.get("url"))].append(j)

    mislukt = Counter()

    def _groep(host, groep):
        tempo = _tempo_voor(host)
        n = workers if workers is not None else tempo["workers"]
        pacer = _Pacer(tempo["pauze"])
        with cf.ThreadPoolExecutor(max_workers=min(n, len(groep))) as ex:
            list(ex.map(lambda j: _een(j, pacer, mislukt), groep))
        gelukt = sum(1 for j in groep if j.get("beschrijving"))
        print(f"[detail] {host}: {gelukt}/{len(groep)} omschrijvingen")

    with cf.ThreadPoolExecutor(max_workers=len(per_host)) as ex:
        list(ex.map(lambda kv: _groep(*kv), per_host.items()))

    for reden, aantal in mislukt.most_common():
        print(f"[detail] mislukt: {reden} x{aantal}")
